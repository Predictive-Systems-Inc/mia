import numpy as np
import pytest

pytestmark = pytest.mark.learning
TINY = "optimum-intel-internal-testing/tiny-random-xlm-roberta"


def test_embedder_returns_unit_rows_and_prefix() -> None:
    from mia.learning.embed import Embedder, prefix_for

    assert prefix_for("intfloat/multilingual-e5-small") == "query: "
    assert prefix_for(TINY) == ""
    e = Embedder(TINY)
    m = e(["hello there", "oon kipee", "x"])
    assert m.shape[0] == 3 and m.dtype == np.float32
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0, atol=1e-5)
    assert e([]).shape[0] == 0
