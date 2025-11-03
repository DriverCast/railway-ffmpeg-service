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

# CORREÇÃO: O 'filename' é o parâmetro de entrada, não o objeto 'file'
def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida."""
    # Garante que o filename não é vazio antes de tentar o rsplit
    if not filename:
        return False
    # Acessa a extensão usando o parâmetro 'filename'
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
    
    # CORREÇÃO DE CHAMADA: Chama allowed_file(file.filename)
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
        
        # Filtro FINAL: 720p vertical (720x1280) para otimização de RAM
        vf_filter = "scale=w=720:h=1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
        
        # COMANDO FINAL: 720p, ALTA QUALIDADE DE IMAGEM (fast/crf 22) + REMOÇÃO DE ÁUDIO (-an)
        ffmpeg_command_string = (
            f"/usr/bin/ffmpeg -y -hide_banner -loglevel error -ss {start} -t {duration} -i {input_path} "
            f"-vf \"{vf_filter}\" " 
            f"-c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p " 
            f"-an " # REMOVE ÁUDIO
            f"-movflags +faststart {output_path}"
        )
        
        # Executa FFmpeg
        result = subprocess.run(
            ffmpeg_command_string, 
            capture_output=True,
            text=True,
            timeout=300, 
            shell=True 
        )
        
        if result.returncode != 0:
            error_message = f"FFmpeg error: {result.stderr}. Command: {ffmpeg_command_string}"
            raise Exception(error_message)
        
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
        # Retorna o erro exato
        return jsonify({'error': str(e)}), 500
        
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
