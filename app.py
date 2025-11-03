"""
Railway FFmpeg Service - API REST para cortar vídeos
Deploy em railway.app (100% FREE)
"""

from flask import Flask, request, send_file, jsonify
import subprocess
import os
import uuid
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configurações
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_timestamp(value):
    """Valida se é número positivo"""
    try:
        num = float(value)
        return num >= 0
    except:
        return False

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'online',
        'service': 'FFmpeg Video Cutter',
        'version': '1.0.0',
        'endpoints': {
            'POST /cut': 'Cut video with start/end timestamps',
            'GET /': 'This health check'
        }
    }), 200

@app.route('/cut', methods=['POST'])
def cut_video():
    """
    Corta vídeo com FFmpeg
    
    Form-data:
    - file: arquivo de vídeo
    - start: timestamp inicial em segundos (ex: 12.5)
    - duration: duração do corte em segundos (ex: 30.0)
    """
    
    # Validação do arquivo
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: mp4, avi, mov, mkv, webm'}), 400
    
    # Validação dos parâmetros
    start = request.form.get('start', '0')
    duration = request.form.get('duration')
    
    if not validate_timestamp(start):
        return jsonify({'error': 'Invalid start timestamp'}), 400
    
    if not duration or not validate_timestamp(duration):
        return jsonify({'error': 'Invalid or missing duration'}), 400
    
    start = float(start)
    duration = float(duration)
    
    # Validação de duração (15-60s)
    if duration < 15 or duration > 60:
        return jsonify({'error': 'Duration must be between 15 and 60 seconds'}), 400
    
    # Gera nomes únicos
    job_id = str(uuid.uuid4())
    input_filename = secure_filename(f"{job_id}_input_{file.filename}")
    output_filename = f"{job_id}_output.mp4"
    
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)
    
    try:
        # Salva arquivo temporário
        file.save(input_path)
        
        # Comando FFmpeg otimizado para shorts (1080x1920)
        ffmpeg_command = [
            '/usr/bin/ffmpeg',
            '-y',  # Sobrescrever sem perguntar
            '-hide_banner',
            '-loglevel', 'error',
            '-ss', str(start),  # Seek antes do input (mais rápido)
            '-t', str(duration),  # Duração
            '-i', input_path,  # Input
            '-vf', "scale='min(1080,iw)':'min(1920,ih)':force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",  # Crop para 9:16
            '-c:v', 'libx264',  # Codec H.264 (compatível)
            '-preset', 'fast',  # Preset rápido
            '-crf', '22',  # Qualidade
            '-pix_fmt', 'yuv420p',  # Compatibilidade
            '-c:a', 'aac',  # Codec de áudio
            '-b:a', '128k',  # Bitrate áudio
            '-ar', '48000',  # Sample rate
            '-ac', '2',  # Stereo
            '-movflags', '+faststart',  # Otimiza para streaming
            output_path
        ]
        
        # Executa FFmpeg
        result = subprocess.run(
            ffmpeg_command,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutos timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        # Verifica se arquivo foi criado
        if not os.path.exists(output_path):
            raise Exception("Output file not created")
        
        # Retorna o arquivo
        response = send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'short_{job_id}.mp4'
        )
        
        # Agenda limpeza dos arquivos temporários
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(input_path):
                    os.remove(input_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception as e:
                print(f"Cleanup error: {e}")
        
        return response
        
    except subprocess.TimeoutExpired:
        # Limpa arquivos em caso de timeout
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        return jsonify({'error': 'Processing timeout (max 5 minutes)'}), 408
        
    except Exception as e:
        # Limpa arquivos em caso de erro
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
