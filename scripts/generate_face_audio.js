const fs = require('fs');
const path = require('path');
const { promisify } = require('util');
const exec = promisify(require('child_process').exec);

// Directorio donde se guardarán los archivos de audio
const outputDir = path.join(__dirname, '../../daw_frontend/public/audio');

// Asegurarnos de que el directorio existe
if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
    console.log(`Directorio creado: ${outputDir}`);
}

// Mensaje para la guía de captura facial
const faceCaptureMessage = 'Ahora activaré la cámara para capturar tu rostro. Por favor, colócate frente a la cámara, mantén el rostro estable y con buena iluminación. La foto se tomará automáticamente cuando se detecte estabilidad.';

// Función para generar audio usando espeak
async function generateAudio(message, filename) {
    const outputPath = path.join(outputDir, `${filename}.mp3`);
    
    try {
        // Usar espeak para generar el audio
        const command = `espeak -v es-mx -s 130 -p 50 "${message}" --stdout | ffmpeg -i - -ar 44100 -ac 2 -ab 192k -f mp3 "${outputPath}"`;
        
        console.log(`Generando audio para: ${filename}`);
        await exec(command);
        console.log(`Audio generado con éxito: ${outputPath}`);
        return true;
    } catch (error) {
        console.error(`Error al generar el audio ${filename}:`, error);
        return false;
    }
}

// Generar el audio de captura facial
async function main() {
    console.log('Generando archivo de audio para captura facial...');
    
    let success = await generateAudio(faceCaptureMessage, 'faceCapture');
    
    if (success) {
        console.log('Todos los archivos de audio de captura facial generados correctamente.');
    } else {
        console.error('Hubo errores al generar los archivos de audio de captura facial.');
    }
}

main().catch(console.error);