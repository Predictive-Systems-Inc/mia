// Uses Groq API — same OpenAI-compatible interface, ~10x faster inference
// Model: llama-3.3-70b-versatile (fast, multilingual, great for conversational AI)

exports.handler = async function (event) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const GROQ_API_KEY = process.env.GROQ_API_KEY;
  if (!GROQ_API_KEY) {
    return { statusCode: 500, body: JSON.stringify({ error: 'Groq API key not configured.' }) };
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: 'Invalid request body.' }) };
  }

  const { messages } = body;
  if (!messages || !Array.isArray(messages)) {
    return { statusCode: 400, body: JSON.stringify({ error: 'Missing messages array.' }) };
  }

  const SYS = `You are Mia, the AI secretary of Dr. Santos Clinic in Quezon City, Philippines.
Your role: book appointments, check schedules, collect basic patient info, answer clinic questions.

Clinic details:
- Doctor: Dr. David Santos, MD — General Practice
- Address: 123 Katipunan Ave., Quezon City
- Hours: Mon–Fri 9am–5pm, Sat 9am–1pm, closed Sundays & holidays
- Available slots: Today has 2:00 PM and 4:00 PM. Tomorrow has 10:00 AM, 2:00 PM, and 3:00 PM.

Rules:
- Be warm, friendly, and professional
- Keep replies SHORT — 2 to 4 sentences max
- If the patient is speaking via voice, avoid bullet points and markdown — use natural spoken language instead
- Respond in the same language the patient uses (Filipino or English)
- Never give medical advice or diagnoses
- Collect patient name, contact number, and reason for visit when booking
- Always confirm the appointment details before finalizing
- If unsure, say you will check with the clinic and get back to them
- You are an AI secretary, NOT a doctor`;

  try {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${GROQ_API_KEY}`,
      },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [{ role: 'system', content: SYS }, ...messages],
        max_tokens: 220,
        temperature: 0.7,
      }),
    });

    const data = await response.json();

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    };
  } catch (err) {
    return {
      statusCode: 502,
      body: JSON.stringify({ error: 'Failed to reach Groq.', detail: err.message }),
    };
  }
};
