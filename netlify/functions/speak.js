// Hume Octave TTS
// Converts Mia's text responses to natural, expressive speech
// Docs: https://dev.hume.ai/docs/text-to-speech-tts/overview

exports.handler = async function (event) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const HUME_API_KEY = process.env.HUME_API_KEY;
  if (!HUME_API_KEY) {
    return { statusCode: 500, body: JSON.stringify({ error: 'Hume API key not configured.' }) };
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: 'Invalid request body.' }) };
  }

  const { text } = body;
  if (!text || typeof text !== 'string') {
    return { statusCode: 400, body: JSON.stringify({ error: 'Missing text field.' }) };
  }

  try {
    const response = await fetch('https://api.hume.ai/v0/tts', {
      method: 'POST',
      headers: {
        'X-Hume-Api-Key': HUME_API_KEY,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        utterances: [
          {
            text: text,
            // Kora: warm, professional, empathetic — ideal for a medical secretary
            // Browse voices at: https://dev.hume.ai/docs/text-to-speech-tts/voices
            voice: { name: 'KORA' },
          },
        ],
        format: { type: 'mp3' },
        // Hume generates emotionally appropriate prosody automatically
        // based on the content — no extra configuration needed
      }),
    });

    if (!response.ok) {
      const err = await response.text();
      return { statusCode: response.status, body: JSON.stringify({ error: err }) };
    }

    const data = await response.json();

    // Hume returns audio as base64 in the response
    // generations[0].audio contains the base64-encoded MP3
    const base64Audio = data.generations?.[0]?.audio;

    if (!base64Audio) {
      return { statusCode: 500, body: JSON.stringify({ error: 'No audio in Hume response.' }) };
    }

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio: base64Audio }),
    };
  } catch (err) {
    return {
      statusCode: 502,
      body: JSON.stringify({ error: 'Failed to reach Hume.', detail: err.message }),
    };
  }
};
