"""Train, calibrate, evaluate and package one role (spec section 5). Needs the learning group."""

import datetime as dt
import hashlib
import random
from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer, PreTrainedTokenizerBase

from mia.learning import catalogue
from mia.learning.gate import check_gate
from mia.learning.metrics import Prediction, choose_thresholds, evaluate, fit_temperature
from mia.learning.package import (
    ARTIFACTS,
    Kind,
    ModelCard,
    active_version,
    read_card,
    write_card,
)
from mia.learning.schema import Record, RoleSpec, load_records, load_role
from mia.settings import get_settings

LANGS = ["en", "fi", "fil", "mixed"]
MAX_LEN = 96
IGNORE = -100


class Heads(nn.Module):  # type: ignore[misc,unused-ignore]  # Any when torch is not installed
    """Shared encoder, intent head, language head, one head per slot."""

    def __init__(self, base: str, n_intents: int, slots: dict[str, list[str]]) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base)
        size = self.encoder.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.intent = nn.Linear(size, n_intents)
        self.lang = nn.Linear(size, len(LANGS))
        self.slots = nn.ModuleDict(
            {name: nn.Linear(size, len(values)) for name, values in slots.items()}
        )

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> tuple[torch.Tensor, ...]:
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]
        h = self.drop(h)
        return (self.intent(h), self.lang(h), *(head(h) for head in self.slots.values()))


def _slot_values(role: RoleSpec, records: list[Record]) -> dict[str, list[str]]:
    names = sorted({s for i in role.intents for s in i.slots})
    return {n: sorted({r.slots[n] for r in records if n in r.slots}) or ["none"] for n in names}


def _batches(records: list[Record], size: int, rng: random.Random) -> list[list[Record]]:
    order = records[:]
    rng.shuffle(order)
    return [order[i : i + size] for i in range(0, len(order), size)]


def _encode(tok: PreTrainedTokenizerBase, batch: list[Record]) -> dict[str, torch.Tensor]:
    enc = tok(
        [r.text for r in batch],
        [r.context or "" for r in batch],
        truncation=True,
        max_length=MAX_LEN,
        padding=True,
        return_tensors="pt",
    )
    return dict(enc)


def _predict(
    model: Heads, tok: PreTrainedTokenizerBase, records: list[Record], labels: list[str]
) -> list[Prediction]:
    model.eval()
    out: list[Prediction] = []
    with torch.no_grad():
        for i in range(0, len(records), 64):
            batch = records[i : i + 64]
            logits = model(**_encode(tok, batch))[0]
            out += [
                Prediction(
                    record_id=r.id,
                    intent=r.intent if r.intent in labels else "other",
                    lang=r.lang,
                    kind=r.kind,
                    style=r.style,
                    labels=labels,
                    logits=row.tolist(),
                )
                for r, row in zip(batch, logits, strict=True)
            ]
    return out


def slot_targets(batch: list[Record], name: str, values: list[str]) -> list[int]:
    """Class index per record for one slot; -100 (ignored by the loss) when missing or unknown."""
    return [values.index(v) if (v := r.slots.get(name)) in values else IGNORE for r in batch]


def _fit(
    base: str,
    tok: PreTrainedTokenizerBase,
    labels: list[str],
    slots: dict[str, list[str]],
    train: list[Record],
    dev: list[Record],
    seed: int,
    epochs: int,
    lr: float = 3e-5,
) -> tuple[Heads, float]:
    torch.manual_seed(seed)
    rng = random.Random(seed)
    model = Heads(base, len(labels), slots)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = max(1, epochs * ((len(train) + 31) // 32))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / (0.06 * steps)) * max(0.0, 1 - s / steps)
    )
    ce = nn.CrossEntropyLoss(label_smoothing=0.1)
    slot_ce = nn.CrossEntropyLoss(ignore_index=IGNORE, label_smoothing=0.1)
    best_state, best_nll, patience = None, float("inf"), 0
    for _ in range(epochs):
        model.train()
        for batch in _batches(train, 32, rng):
            out = model(**_encode(tok, batch))
            y = torch.tensor(
                [labels.index(r.intent) if r.intent in labels else len(labels) - 1 for r in batch]
            )
            loss = ce(out[0], y) + 0.3 * ce(
                out[1], torch.tensor([LANGS.index(r.lang) for r in batch])
            )
            for k, (name, values) in enumerate(slots.items()):
                ys = torch.tensor(slot_targets(batch, name, values))
                if (ys != IGNORE).any():  # mean over zero targets would be NaN
                    loss = loss + 0.2 * slot_ce(out[2 + k], ys)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
        preds = _predict(model, tok, dev, labels)
        nll = -sum(
            torch.log_softmax(torch.tensor(p.logits), 0)[labels.index(p.intent)].item()
            for p in preds
        )
        if nll < best_nll:
            best_nll, best_state, patience = (
                nll,
                {k: v.clone() for k, v in model.state_dict().items()},
                0,
            )
        else:
            patience += 1
            if patience >= 3:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_nll


def _export(
    model: Heads, tok: PreTrainedTokenizerBase, out: Path, slots: dict[str, list[str]]
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    model.eval()
    sample = _encode(
        tok,
        [
            Record(
                id="x",
                role="x",
                intent="other",
                lang="en",
                text="hello",
                counterpart="x",
                style="terse",
                split="train",
                source="export",
            )
        ],
    )
    names = ["intent_logits", "lang_logits", *(f"slot_{n}_logits" for n in slots)]
    torch.onnx.export(
        model,
        (sample["input_ids"], sample["attention_mask"]),
        out / "model.onnx",
        input_names=["input_ids", "attention_mask"],
        output_names=names,
        dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}},
        opset_version=17,
        dynamo=False,
    )
    backend = getattr(tok, "backend_tokenizer", None)  # fast (tokenizers) backend only
    if backend is None:
        raise ValueError("base model has no fast tokenizer; tokenizer.json cannot be exported")
    # The runtime encodes with tokenizer.json alone: pin truncation as training used it.
    backend.enable_truncation(max_length=MAX_LEN)
    backend.save(str(out / "tokenizer.json"))
    if (out / "model.onnx").stat().st_size > 50_000_000:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        quantize_dynamic(out / "model.onnx", out / "model.int8.onnx", weight_type=QuantType.QInt8)
        (out / "model.int8.onnx").replace(out / "model.onnx")


def _report(card: ModelCard, curve: dict[int, float]) -> str:
    rep = card.report
    lines = [
        f"# {card.role} {card.version}",
        "",
        f"Kind: {card.kind}. Base model: {card.base_model}. Data hash: {card.data_hash}.",
        f"Gate: {'passed' if card.gate.passed else 'failed'}",
        *(f"- {f}" for f in card.gate.failures),
        "",
        (
            f"Accuracy {rep.accuracy:.3f}, macro-F1 {rep.macro_f1:.3f}, "
            f"coverage {rep.coverage:.2f}, ECE {rep.ece:.3f}, "
            f"safety recall {rep.safety_recall:.3f}, false emergency {rep.false_emergency:.3f}, "
            f"actions from other {rep.actions_from_other}"
        ),
        "",
        "| Language | Accuracy |",
        "|---|---|",
        *(f"| {k} | {v:.3f} |" for k, v in sorted(rep.per_lang.items())),
        "",
        "| Intent | Support | Precision at threshold | Recall | Auto share |",
        "|---|---|---|---|---|",
        *(
            f"| {k} | {s.support} | {s.precision_at_threshold:.3f} | {s.recall:.3f} | {s.auto_share:.2f} |"
            for k, s in rep.per_intent.items()
        ),
        "",
        *(
            [
                "Learning curve (share of train: test accuracy): "
                + ", ".join(f"{k}%: {v:.3f}" for k, v in curve.items()),
                "",
            ]
            if curve
            else []
        ),
        "Most confused: " + "; ".join(f"{a} -> {b} ({n})" for a, b, n in rep.confusions[:10]),
        "",
        "Sign-off: pending (mia skills promote ... --signed-by NAME)",
    ]
    return "\n".join(lines) + "\n"


def load_splits(
    folder: Path, with_real: bool = False
) -> tuple[RoleSpec, list[Record], list[Record], list[Record]]:
    """role.yaml and the three splits; with_real adds kept or fixed local candidates (D18)."""
    role = load_role(folder / "role.yaml")
    data = folder / "data"
    train, dev, test = (load_records(data / f"{s}.jsonl") for s in ("train", "dev", "test"))
    if with_real:
        real = get_settings().MIA_LEARNING_DIR / role.id / "candidates.jsonl"
        approved = (
            [r for r in load_records(real) if r.review.status in ("kept", "fixed")]
            if real.exists()
            else []
        )
        train += [r for r in approved if r.split == "train"]
        dev += [r for r in approved if r.split == "dev"]
    return role, train, dev, test


def new_version(kind: str = "encoder") -> str:
    """v<UTC YYYYMMDDHHMM>, with -<kind> appended for every kind but encoder."""
    stamp = "v" + dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    return stamp if kind == "encoder" else f"{stamp}-{kind}"


def new_package_dir(role_id: str, version: str) -> Path:
    """The (not yet created) package directory; raises FileExistsError if it already exists."""
    out = get_settings().MIA_MODELS_DIR / role_id / version
    if out.exists():
        raise FileExistsError(f"{role_id}@{version} already exists; refusing to overwrite")
    return out


def package(
    *,
    folder: Path,
    role: RoleSpec,
    kind: Kind,
    base: str,
    prefix: str,
    labels: list[str],
    slots: dict[str, list[str]],
    train: list[Record],
    dev: list[Record],
    test: list[Record],
    dev_preds: list[Prediction],
    test_preds: list[Prediction],
    curve: dict[int, float],
    out: Path,
    version: str,
    with_real: bool,
) -> ModelCard:
    """Calibrates on dev, evaluates on test, gates, hashes ARTIFACTS[kind] in out, writes the
    card (with_real marks a package trained on local real messages, D18) and the report. The
    exported files must already be in out."""
    conversation = {c.id: c.handling for c in catalogue.conversation_intents()}
    temperature = fit_temperature(dev_preds)
    thresholds = choose_thresholds(dev_preds, role, temperature, conversation)
    report = evaluate(
        test_preds, role, thresholds, temperature, catalogue.safety_ids(), conversation
    )
    previous = active_version(role.id)
    gate = check_gate(report, role, read_card(role.id, previous).report if previous else None)
    digest = hashlib.sha256(
        "".join(r.model_dump_json() for r in train + dev + test).encode()
    ).hexdigest()[:16]
    card = ModelCard(
        role=role.id,
        version=version,
        kind=kind,
        prefix=prefix,
        base_model=base,
        data_hash=digest,
        temperature=temperature,
        medium_floor=role.targets.medium_floor,
        safety_floor=role.targets.safety_floor,
        labels=labels,
        langs=LANGS,
        slots=slots,
        thresholds=thresholds,
        report=report,
        gate=gate,
        artifacts={n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in ARTIFACTS[kind]},
        with_real=with_real,
    )
    write_card(card)
    (folder / "reports").mkdir(exist_ok=True)
    (folder / "reports" / f"{version}.md").write_text(_report(card, curve), encoding="utf-8")
    return card


def train_role(
    folder: Path,
    base_model: str | None = None,
    with_real: bool = False,
    seeds: tuple[int, ...] = (0, 1, 2),
    epochs: int = 20,
) -> ModelCard:
    role, train, dev, test = load_splits(folder, with_real)
    base = base_model or role.base_model
    conversation = {c.id: c.handling for c in catalogue.conversation_intents()}
    labels = role.label_space(list(conversation))
    slots = _slot_values(role, train)
    tok = AutoTokenizer.from_pretrained(base)
    runs = [_fit(base, tok, labels, slots, train, dev, s, epochs) for s in seeds]
    model, _ = min(runs, key=lambda x: x[1])
    dev_preds = _predict(model, tok, dev, labels)
    test_preds = _predict(model, tok, test, labels)
    # The curve needs the same calibration package() derives (deterministic from dev_preds).
    temperature = fit_temperature(dev_preds)
    thresholds = choose_thresholds(dev_preds, role, temperature, conversation)
    safety = catalogue.safety_ids()
    curve: dict[int, float] = {}
    for share in (25, 50, 75):
        part = random.Random(0).sample(train, max(1, len(train) * share // 100))
        m, _ = _fit(base, tok, labels, slots, part, dev, seeds[0], max(1, epochs // 2))
        curve[share] = evaluate(
            _predict(m, tok, test, labels), role, thresholds, temperature, safety, conversation
        ).accuracy
    curve[100] = evaluate(test_preds, role, thresholds, temperature, safety, conversation).accuracy
    version = new_version()
    out = new_package_dir(role.id, version)
    _export(model, tok, out, slots)
    return package(
        folder=folder,
        role=role,
        kind="encoder",
        base=base,
        prefix="",
        labels=labels,
        slots=slots,
        train=train,
        dev=dev,
        test=test,
        dev_preds=dev_preds,
        test_preds=test_preds,
        curve=curve,
        out=out,
        version=version,
        with_real=with_real,
    )
