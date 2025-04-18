const AWS = require('aws-sdk');
const { validationResult } = require('express-validator');

// Configurar AWS con credenciales del entorno o archivo de configuración
AWS.config.update({
  region: process.env.AWS_REGION || 'us-east-1',
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
});

// Crear una instancia de Polly
const polly = new AWS.Polly();

/**
 * Controlador para sintetizar voz usando Amazon Polly
 * @param {Object} req - Objeto de solicitud Express
 * @param {Object} res - Objeto de respuesta Express
 */
exports.synthesizeSpeech = async (req, res) => {
  try {
    // Validar la solicitud
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ errors: errors.array() });
    }

    const { text, voiceId = 'Conchita', languageCode = 'es-ES' } = req.body;

    // Verificar texto
    if (!text || text.trim() === '') {
      return res.status(400).json({ message: 'No text provided for synthesis' });
    }

    // Parámetros para la síntesis
    const params = {
      Text: text,
      OutputFormat: 'mp3',
      VoiceId: voiceId,
      LanguageCode: languageCode,
      Engine: 'neural' // Usar motor neural para mejor calidad
    };

    console.log(`Solicitando síntesis para: "${text}" con voz: ${voiceId}`);

    // Solicitar síntesis a Polly
    const result = await polly.synthesizeSpeech(params).promise();
    
    // Establecer encabezados para audio
    res.set({
      'Content-Type': 'audio/mpeg',
      'Content-Length': result.AudioStream.length
    });

    // Enviar el audio como respuesta
    res.send(result.AudioStream);
    
  } catch (error) {
    console.error('Error en Polly Controller:', error);
    res.status(500).json({ 
      message: 'Error en la síntesis de voz', 
      error: error.message || 'Unknown error' 
    });
  }
};

/**
 * Obtener las voces disponibles en Amazon Polly
 */
exports.getVoices = async (req, res) => {
  try {
    const { languageCode } = req.query;
    
    const params = {};
    if (languageCode) {
      params.LanguageCode = languageCode;
    }
    
    const result = await polly.describeVoices(params).promise();
    
    res.json(result.Voices);
  } catch (error) {
    console.error('Error obteniendo voces:', error);
    res.status(500).json({ 
      message: 'Error al obtener voces disponibles', 
      error: error.message 
    });
  }
}; 