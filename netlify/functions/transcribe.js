// Whisper STT via Groq API
// Accepts base64-encoded audio from the browser MediaRecorder
// Returns the transcribed text

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

  const { audio, mimeType = 'audio/webm' } = body;
  if (!audio) {
    return { statusCode: 400, body: JSON.stringify({ error: 'Missing audio field.' }) };
  }

  try {
    // Decode base64 audio from browser
    const buffer = Buffer.from(audio, 'base64');
    const blob = new Blob([buffer], { type: mimeType });

    const formData = new FormData();
    formData.append('file', blob, 'audio.webm');
    formData.append('model', 'whisper-large-v3');
    formData.append('language', 'en'); // handles Filipino-English code-switching well
    formData.append('response_format', 'json');
    formData.append('temperature', '0');

    const response = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${GROQ_API_KEY}`,
        // Do NOT set Content-Type — fetch sets it automatically with boundary for FormData
      },
      body: formData,
    });

    if (!response.ok) {
      const err = await response.text();
      return { statusCode: response.status, body: JSON.stringify({ error: err }) };
    }

    const data = await response.json();

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: data.text }),
    };
  } catch (err) {
    return {
      statusCode: 502,
      body: JSON.stringify({ error: 'Failed to reach Groq Whisper.', detail: err.message }),
    };
  }
};
