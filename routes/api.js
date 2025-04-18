const express = require('express');
const router = express.Router();
const { body } = require('express-validator');

// Importar controladores
const pollyController = require('../controllers/pollyController');

// Rutas para Amazon Polly
router.post('/synthesize', [
  body('text').notEmpty().withMessage('El texto no puede estar vacío'),
  body('voiceId').optional().isString(),
  body('languageCode').optional().isString()
], pollyController.synthesizeSpeech);

router.get('/voices', pollyController.getVoices);

// Exportar router
module.exports = router; 