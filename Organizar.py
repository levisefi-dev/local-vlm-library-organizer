import os
import shutil
import json
import requests
import base64
import time
import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import difflib
import re
import xml.etree.ElementTree as ET

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_TEXTO_LOCAL = "Gemma4:e4b"
ARCHIVO_MEMORIA = "memoria_categorias.json"
MODELO_VISION_LOCAL = "llava" # Cambia esto por tu modelo multimodal en Ollama

# ==========================================
# MEMORIA Y FILTRADO (El Cadenero)
# ==========================================
def cargar_memoria():
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

def guardar_memoria(categorias):
    with open(ARCHIVO_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(categorias, f, ensure_ascii=False, indent=4)

def aplicar_cadenero(temas_crudos, categorias_conocidas):
    temas_finales = []
    for tema_sugerido in temas_crudos:
        tema_str = str(tema_sugerido).strip().title()
        if not tema_str or tema_str.lower() in ['unclassified', 'unknown', 'others']:
            continue
        coincidencias = difflib.get_close_matches(tema_str, categorias_conocidas, n=1, cutoff=0.8)
        if coincidencias:
            temas_finales.append(coincidencias[0])
        else:
            categorias_conocidas.append(tema_str)
            temas_finales.append(tema_str)
            print(f"    * Nueva categoría aprendida: '{tema_str}'")
    if not temas_finales: temas_finales = ["Others"]
    return list(set(temas_finales))

# ==========================================
# EXTRACCIÓN Y DETECCIÓN
# ==========================================
def extraer_texto(ruta_archivo):
    ext = ruta_archivo.lower().split('.')[-1]
    texto = ""
    try:
        if ext == 'pdf':
            # Context manager asegura que el archivo se libere de la memoria RAM
            with fitz.open(ruta_archivo) as doc:
                for page_num in range(min(4, doc.page_count)):
                    texto += doc.load_page(page_num).get_text()
        elif ext == 'epub':
            book = epub.read_epub(ruta_archivo)
            items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            for item in items[:4]: 
                soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                texto += soup.get_text()
    except: pass
    return texto[:4000].strip()

def extraer_portadas_base64(ruta_archivo):
    try:
        imagenes = []
        with fitz.open(ruta_archivo) as doc:
            for i in range(min(2, doc.page_count)):
                pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
                imagenes.append(base64.b64encode(pix.tobytes("png")).decode('utf-8'))
        return imagenes
    except: return []

def buscar_isbn(texto, filename):
    patron = re.compile(r'(?:97[89]-?)?[0-9\-]{10,17}')
    match_file = patron.search(filename)
    if match_file:
        limpio = re.sub(r'[\-\s]', '', match_file.group(0))
        if len(limpio) in [10, 13]: return limpio
    match_text = re.search(r'ISBN(?:-13|-10)?[\s:]*([0-9\-X]{10,17})', texto, re.IGNORECASE)
    if match_text:
        limpio = re.sub(r'[\-\s]', '', match_text.group(1))
        if len(limpio) in [10, 13]: return limpio
    return None

def buscar_arxiv_id(texto, filename):
    patron = re.compile(r'(\d{4}\.\d{4,5}(?:v\d+)?)')
    match_file = patron.search(filename)
    if match_file: return match_file.group(1)
    match_text = re.search(r'arxiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)', texto, re.IGNORECASE)
    return match_text.group(1) if match_text else None

# ==========================================
# CONEXIONES (API Y IA)
# ==========================================
def consultar_open_library(isbn, categorias_conocidas):
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        llave = f"ISBN:{isbn}"
        if llave in data:
            libro = data[llave]
            temas_crudos = []
            for s in libro.get('subjects', [])[:4]:
                partes = str(s['name']).split('/')
                for p in partes:
                    temas_crudos.append(p.strip())
            return {
                "titulo": libro.get('title', 'Unknown'), 
                "autor": libro.get('authors', [{'name': 'Unknown'}])[0]['name'], 
                "temas": aplicar_cadenero(temas_crudos, categorias_conocidas)
            }
    except: pass
    return None

def consultar_arxiv(arxiv_id, categorias_conocidas):
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
            entry = root.find('atom:entry', ns)
            if entry is not None:
                titulo = entry.find('atom:title', ns).text.replace('\n', ' ').strip()
                autor = entry.find('atom:author/atom:name', ns).text.strip()
                cat_tag = entry.find('arxiv:primary_category', ns)
                categoria_cruda = cat_tag.attrib['term'] if cat_tag is not None else 'math'
                
                mapa_categorias = {'math': 'Mathematics', 'cs': 'Computer Science', 'physics': 'Physics'}
                tema_limpio = mapa_categorias.get(categoria_cruda.split('.')[0], 'Science')
                return {"titulo": titulo, "autor": autor, "temas": aplicar_cadenero([tema_limpio], categorias_conocidas)}
    except: pass
    return None

def analizar_con_gemma(texto, categorias_conocidas):
    prompt = f"""Extract title, author, and up to 4 broad categories in English. 
    Format: JSON {{"titulo": "X", "autor": "Y", "temas": ["Z"]}}. Text: {texto}"""
    try:
        response = requests.post(OLLAMA_URL, json={"model": MODELO_TEXTO_LOCAL, "prompt": prompt, "stream": False, "format": "json"}, timeout=45)
        data = response.json().get('response', '')
        inicio, fin = data.find('{'), data.rfind('}')
        metadata = json.loads(data[inicio:fin+1])
        metadata['temas'] = aplicar_cadenero(metadata.get('temas', []), categorias_conocidas)
        return metadata
    except: return None

def analizar_portadas_local(imagenes_b64, categorias_conocidas):
    print(f"    [VisiON] Analizando {len(imagenes_b64)} portada(s) en local con {MODELO_VISION_LOCAL}...")
    
    # PROMPT ACTUALIZADO: Más estricto para forzar disciplinas científicas
    prompt = """Analyze these academic book/document covers. Extract the main title, author, and up to 2 broad categories in English. 
    CRITICAL INSTRUCTION FOR CATEGORIES: Strongly prefer hard science disciplines (e.g., 'Mathematics', 'Physics', 'Computer Science', 'Algebraic Geometry'). Do NOT use generic terms like 'Education', 'Books', or 'Science'.
    Return ONLY a valid JSON format: {"titulo": "X", "autor": "Y", "temas": ["Z"]}"""
    
    payload = {
        "model": MODELO_VISION_LOCAL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "images": imagenes_b64  
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90)
        
        if response.status_code == 200:
            data = response.json().get('response', '')
            inicio = data.find('{')
            fin = data.rfind('}')
            
            if inicio != -1 and fin != -1:
                metadata = json.loads(data[inicio:fin+1])
                metadata['temas'] = aplicar_cadenero(metadata.get('temas', []), categorias_conocidas)
                return metadata
    except Exception as e:
        print(f"    [!] Error en visión local: {e}")
        
    return None

# ==========================================
# PROCESO PRINCIPAL
# ==========================================
def organizar_biblioteca(carpeta):
    memoria = cargar_memoria()
    print("=== Iniciando Organizador Maestro (Full Stack) ===")

    for archivo in os.listdir(carpeta):
        if not archivo.lower().endswith(('.pdf', '.epub')): continue
        
        ruta_full = os.path.join(carpeta, archivo)
        print(f"\nProcesando: {archivo}")
        metadata = None
        texto = extraer_texto(ruta_full)

        # FASE 1: Metadatos Oficiales (OpenLibrary)
        isbn = buscar_isbn(texto, archivo)
        if isbn:
            print(f" -> [Phase 1] ISBN detectado: {isbn}")
            metadata = consultar_open_library(isbn, memoria)
            if metadata: 
                print("    [ÉXITO] Datos descargados de OpenLibrary gratis.")
            
        # FASE 1.5: Metadatos Científicos (arXiv)
        if not metadata:
            arxiv_id = buscar_arxiv_id(texto, archivo)
            if arxiv_id:
                print(f" -> [Phase 1.5] arXiv ID detectado: {arxiv_id}")
                metadata = consultar_arxiv(arxiv_id, memoria)
                if metadata: 
                    print("    [ÉXITO] Datos descargados de arXiv gratis.")
                time.sleep(3) 

        # FASE 2: Gemma (Local)
        if not metadata and texto and len(texto) > 100:
            print(" -> [Phase 2] Gemma Local...")
            metadata = analizar_con_gemma(texto, memoria)

        # FASE 3: Visión Multimodal (Local vía Ollama)
        if not metadata and archivo.lower().endswith('.pdf'):
            print(" -> [Phase 3] Visión Local (Ollama)...")
            fotos = extraer_portadas_base64(ruta_full)
            if fotos: 
                metadata = analizar_portadas_local(fotos, memoria)

        # FALLBACK
        if not metadata:
            metadata = {"titulo": archivo.split('.')[0], "autor": "Unknown", "temas": ["Manual Review"]}

        # --- LÓGICA DE GUARDADO Y ELIMINACIÓN ---
        temas = metadata.get('temas', ['Others'])
        chars_malos = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        
        titulo_ia = str(metadata.get('titulo', '')).strip()
        autor_ia = str(metadata.get('autor', '')).strip()
        
        # FALLBACK INTELIGENTE: Si la IA devuelve basura, conserva el nombre original del archivo
        if not titulo_ia or titulo_ia.lower() in ['none', 'null', 'unknown', 'untitled']:
            titulo = os.path.splitext(archivo)[0] 
            autor = "Unknown Author"
        else:
            titulo = titulo_ia[:80]
            autor = autor_ia[:40]

        for c in chars_malos:
            titulo = titulo.replace(c, '-')
            autor = autor.replace(c, '-')
            
        nuevo_nombre = f"{titulo.strip()} - {autor.strip()}{os.path.splitext(archivo)[1]}"

        # IMPRESIÓN AÑADIDA PARA OBSERVABILIDAD EN LA TERMINAL
        print(f"    [ETIQUETA FINAL] -> {nuevo_nombre}")

        for i, tema in enumerate(temas):
            tema_str = str(tema)[:40]
            for c in chars_malos:
                tema_str = tema_str.replace(c, '-')
            tema_limpio = tema_str.strip().title()
            
            tema_dir = os.path.join(carpeta, tema_limpio)
            os.makedirs(tema_dir, exist_ok=True)
            destino = os.path.join(tema_dir, nuevo_nombre)

            if i == len(temas) - 1:
                try:
                    shutil.move(ruta_full, destino)
                    print(f" -> [MOVED] Finalizado en: {tema_limpio}")
                except Exception as e: print(f" Error moviendo: {e}")
            else:
                try:
                    shutil.copy(ruta_full, destino)
                    print(f" -> [COPIED] Agregado a: {tema_limpio}")
                except Exception as e: print(f" Error copiando: {e}")

        guardar_memoria(memoria)

if __name__ == "__main__":
    organizar_biblioteca('.')
    print("\n¡Organización completa!")