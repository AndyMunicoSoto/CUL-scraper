"""
CUL — Descarga automática del Certificado Único Laboral
=========================================================
Lee DNI y contraseña desde la tabla 'vendedor' de MySQL,
hace login en empleosperu.gob.pe, resuelve el CAPTCHA con
EasyOCR y descarga el PDF de cada trabajador.

Estructura de carpetas que genera:
    pdfs/
    └── GARCIA_LOPEZ_JUAN/
        └── CUL_GARCIA_LOPEZ_JUAN_2026-06-25.pdf

Uso:
    python main.py

Requisitos:
    pip install selenium easyocr mysql-connector-python
    Google Chrome instalado
"""

import os
import re
import time
import urllib.request
import http.cookiejar
import traceback
from datetime import date
from pathlib import Path

import easyocr
import mysql.connector

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN — edita solo esta sección
# ══════════════════════════════════════════════════════════════════════════════

# Base de datos
DB_HOST     = "192.168.10.149"
DB_USER     = "usuario_python"
DB_PASSWORD = "prueba123"
DB_NAME     = "pllastda"

# Tabla y columnas
TABLA        = "vendedor"
COL_APELLIDOS = "Apellidos"   # columna con el nombre del trabajador
COL_DNI       = "DNI"         # columna con el DNI
COL_PASS      = "Pass_cul"    # columna con la contraseña del portal

# Carpeta donde se guardarán los PDFs (subcarpeta por trabajador)
CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_PDFS   = os.path.join(CARPETA_SCRIPT, "pdfs")

# Portal
LOGIN_URL = "https://www.empleosperu.gob.pe/portal-mtpe/#/login"

# Reintentos
MAX_INTENTOS_LOGIN   = 3   # veces que reintenta el login si el CAPTCHA falla
MAX_REFRESH_CAPTCHA  = 5   # veces que refresca la imagen si el OCR da texto inválido


# ══════════════════════════════════════════════════════════════════════════════
# SELECTORES HTML
# ══════════════════════════════════════════════════════════════════════════════

SEL_TIPO_DOC          = (By.ID, "cboTipoDocumento")
SEL_DNI               = (By.ID, "sNumeroDocumentoIdentidad")
SEL_CONTRASENA        = (By.ID, "password")
SEL_CAPTCHA_IMG       = (By.CSS_SELECTOR, "img[src^='blob:']")
SEL_CAPTCHA_INPUT     = (By.ID, "captcha")
SEL_BTN_ACCEDER       = (By.CSS_SELECTOR, "button[type='submit']")
SEL_SWAL_CONFIRMAR    = (By.CSS_SELECTOR, "button.swal2-confirm")
SEL_SWAL_TITULO       = (By.CSS_SELECTOR, "#swal2-title")
SEL_BTN_OBTENER_CUL   = (By.XPATH, "//button[contains(@class,'btn-danger') and contains(.,'Certificado')]")
SEL_BTN_GENERAR_CUL   = (By.ID, "solicitar")
SEL_BTN_GUARDAR       = (By.XPATH, "//a[contains(@class,'btn-light') and contains(.,'Guardar')]")
SEL_BTN_VER_CARPETA   = (By.XPATH, "//a[contains(., 'Ver mi carpeta')]")
SEL_PRIMER_CERT       = (By.XPATH, "(//a[contains(@href,'Certificado.html')])[1]")


# ══════════════════════════════════════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

def obtener_trabajadores() -> list[dict]:
    """
    Conecta a MySQL y devuelve la lista de trabajadores que tienen
    DNI y Pass_cul cargados en la tabla vendedor.
    """
    print("  Conectando a la base de datos...")
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    query = f"""
        SELECT {COL_APELLIDOS}, {COL_DNI}, {COL_PASS}
        FROM {TABLA}
        WHERE {COL_DNI}  IS NOT NULL AND {COL_DNI}  != ''
          AND {COL_PASS} IS NOT NULL AND {COL_PASS} != ''
        ORDER BY {COL_APELLIDOS}
    """
    cursor.execute(query)
    trabajadores = cursor.fetchall()

    cursor.close()
    conn.close()

    print(f"  {len(trabajadores)} trabajadores encontrados con credenciales.")
    return trabajadores


# ══════════════════════════════════════════════════════════════════════════════
# DRIVER DE CHROME
# ══════════════════════════════════════════════════════════════════════════════

def crear_driver(carpeta_descarga: str) -> webdriver.Chrome:
    """
    Crea Chrome configurado para descargar PDFs automáticamente
    en la carpeta indicada, sin abrir el visor interno de Chrome.
    """
    opciones = Options()

    # ── Para depurar: comenta la siguiente línea para ver Chrome ──
    # opciones.add_argument("--headless=new")

    opciones.add_argument("--window-size=1280,800")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-dev-shm-usage")
    opciones.add_argument("--disable-features=PdfInlineViewer")
    opciones.add_argument("--disable-pdf-viewer")
    opciones.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    opciones.add_experimental_option("excludeSwitches", ["enable-logging"])

    # Descarga automática sin diálogo
    prefs = {
        "download.default_directory":        carpeta_descarga,
        "download.prompt_for_download":       False,
        "download.directory_upgrade":         True,
        "plugins.always_open_pdf_externally": True,
    }
    opciones.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(options=opciones)


# ══════════════════════════════════════════════════════════════════════════════
# CAPTCHA
# ══════════════════════════════════════════════════════════════════════════════

# El Reader se crea UNA sola vez fuera de las funciones para no recargar
# el modelo de EasyOCR en cada iteración (es lento, ~3 segundos la primera vez)
print("  Cargando modelo EasyOCR (solo ocurre una vez)...")
OCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)
print("  Modelo cargado ✓")


def extraer_captcha(wait: WebDriverWait, carpeta: str) -> str:
    """
    Toma una captura del elemento <img> del CAPTCHA y la guarda
    como 'captcha.png' en la carpeta del trabajador.
    Retorna la ruta del archivo guardado.
    """
    img_elem = wait.until(EC.presence_of_element_located(SEL_CAPTCHA_IMG))
    ruta = os.path.join(carpeta, "captcha.png")
    img_elem.screenshot(ruta)
    return ruta


def leer_captcha_ocr(ruta_imagen: str) -> str:
    """
    Lee el texto del CAPTCHA con EasyOCR.
    Devuelve el texto en mayúsculas sin espacios.
    """
    resultados = OCR_READER.readtext(ruta_imagen, detail=0)
    if not resultados:
        raise RuntimeError("El OCR no detectó texto en la imagen del CAPTCHA.")
    texto = resultados[0].replace(" ", "").strip().upper()
    return texto


def refrescar_captcha(wait: WebDriverWait):
    """Hace clic en la imagen para que el portal genere una nueva."""
    img_elem = wait.until(EC.element_to_be_clickable(SEL_CAPTCHA_IMG))
    img_elem.click()
    time.sleep(1)


def llenar_campo_captcha(wait: WebDriverWait, texto: str):
    """Escribe el texto resuelto en el campo de texto del CAPTCHA."""
    campo = wait.until(EC.presence_of_element_located(SEL_CAPTCHA_INPUT))
    campo.clear()
    campo.send_keys(texto)


# ══════════════════════════════════════════════════════════════════════════════
# FORMULARIO DE LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def seleccionar_tipo_dni(driver: webdriver.Chrome, wait: WebDriverWait):
    """Selecciona 'DNI' en el desplegable de tipo de documento."""
    select_elem = wait.until(EC.presence_of_element_located(SEL_TIPO_DOC))
    driver.execute_script(
        "arguments[0].value = '10080399';"
        "arguments[0].dispatchEvent(new Event('change'));",
        select_elem
    )


def llenar_dni(wait: WebDriverWait, dni: str):
    """Escribe el DNI en su campo."""
    campo = wait.until(EC.presence_of_element_located(SEL_DNI))
    campo.clear()
    campo.send_keys(str(dni).strip())


def llenar_contrasena(wait: WebDriverWait, contrasena: str):
    """Escribe la contraseña en su campo."""
    campo = wait.until(EC.presence_of_element_located(SEL_CONTRASENA))
    campo.clear()
    campo.send_keys(str(contrasena).strip())


def hacer_clic_acceder(wait: WebDriverWait):
    """Espera que el botón Acceder se habilite y le hace clic."""
    btn = wait.until(EC.element_to_be_clickable(SEL_BTN_ACCEDER))
    btn.click()


# ══════════════════════════════════════════════════════════════════════════════
# POPUPS Y MODALES
# ══════════════════════════════════════════════════════════════════════════════

def cerrar_popup_swal(wait: WebDriverWait) -> str:
    """
    Espera un popup SweetAlert2, lee su título, hace clic en Aceptar
    y devuelve el título leído.
    """
    btn = wait.until(EC.element_to_be_clickable(SEL_SWAL_CONFIRMAR))
    try:
        titulo = wait.until(EC.presence_of_element_located(SEL_SWAL_TITULO)).text.strip()
    except Exception:
        titulo = "(sin título)"
    btn.click()
    return titulo


def cerrar_modal_banner(driver: webdriver.Chrome, wait: WebDriverWait):
    """
    Cierra el modal de bienvenida con carrusel de banners.
    Intenta tres estrategias en orden: Escape, JS clic, eliminar del DOM.
    """
    SELECTORES_MODAL = [
        (By.CSS_SELECTOR, ".modal-backdrop"),
        (By.CSS_SELECTOR, "ngb-modal-backdrop"),
        (By.CSS_SELECTOR, "ngb-modal-window"),
    ]

    modal_encontrado = False
    for selector in SELECTORES_MODAL:
        try:
            wait.until(EC.presence_of_element_located(selector))
            modal_encontrado = True
            break
        except Exception:
            continue

    if not modal_encontrado:
        return   # No hay modal, continuar normalmente

    time.sleep(0.5)

    # Estrategia 1: Escape
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.8)
        if not driver.find_elements(By.CSS_SELECTOR, "ngb-modal-window"):
            return
    except Exception:
        pass

    # Estrategia 2: JS clic en el backdrop
    try:
        backdrop = driver.find_element(By.CSS_SELECTOR, ".modal-backdrop")
        driver.execute_script("arguments[0].click()", backdrop)
        time.sleep(0.8)
        if not driver.find_elements(By.CSS_SELECTOR, "ngb-modal-window"):
            return
    except Exception:
        pass

    # Estrategia 3: Eliminar del DOM directamente
    driver.execute_script("""
        ['ngb-modal-backdrop', 'ngb-modal-window'].forEach(function(tag) {
            var el = document.querySelector(tag);
            if (el) el.remove();
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
    """)


# ══════════════════════════════════════════════════════════════════════════════
# FLUJO DEL CUL
# ══════════════════════════════════════════════════════════════════════════════

def click_obtener_certificado(driver: webdriver.Chrome, wait: WebDriverWait):
    """
    Hace clic en el botón 'Certificado Único Laboral' de la barra de navegación.
    Si se abre una pestaña nueva, cambia el foco a ella.
    """
    ventanas_antes = set(driver.window_handles)
    btn = wait.until(EC.element_to_be_clickable(SEL_BTN_OBTENER_CUL)) 
    #SEL_BTN_OBTENER_CUL   = (By.XPATH, "//button[contains(@class,'btn-danger') and contains(.,'Certificado')]")
    btn.click()

    try:
        WebDriverWait(driver, 5).until(
            lambda d: len(d.window_handles) > len(ventanas_antes)
        )
        nueva_pestana = (set(driver.window_handles) - ventanas_antes).pop()
        driver.switch_to.window(nueva_pestana)
    except Exception:
        pass   # No se abrió nueva pestaña, continuar en la misma


def generar_y_descargar_cul(driver: webdriver.Chrome, wait: WebDriverWait,
                             nombre_trabajador: str, carpeta: str):
    """
    Flujo completo dentro de la página del CUL:
      1. Clic en 'Generar Certificado Único Laboral'
      2. Confirma en el modal
      3. Espera que el portal procese
      4. Clic en 'Ver mi carpeta de certificados'
      5. Clic en el primer certificado
      6. Descarga el PDF via urllib con las cookies de sesión
      7. Renombra el archivo con el nombre del trabajador y la fecha
    """
    # ── Paso 1: Generar ────────────────────────────────────────────────────
    print("    Buscando botón 'Generar Certificado'...")
    btn_generar = wait.until(EC.element_to_be_clickable(SEL_BTN_GENERAR_CUL))
    btn_generar.click()

    # ── Paso 2: Confirmar en el modal ──────────────────────────────────────
    print("    Confirmando en el modal...")
    btn_confirmar = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(SEL_BTN_GUARDAR)
    )
    btn_confirmar.click()

    # ── Paso 3: Esperar que el portal procese ──────────────────────────────
    print("    Esperando que el portal procese el CUL...")
    WebDriverWait(driver, 60).until(
        lambda d: (
            "ConfirmarSolicitud" in d.current_url
            or len(d.find_elements(By.ID, "solicitar")) == 0
            or not d.find_elements(By.ID, "solicitar")[0].is_enabled()
        )
    )

    # ── Paso 4: Ver carpeta de certificados ───────────────────────────────
    time.sleep(1)
    print("    Abriendo carpeta de certificados...")
    btn_carpeta = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable(SEL_BTN_VER_CARPETA)
    )
    btn_carpeta.click()

    # ── Paso 5: Primer certificado ─────────────────────────────────────────
    time.sleep(2)
    print("    Abriendo el certificado más reciente...")
    primer_cert = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable(SEL_PRIMER_CERT)
    )
    primer_cert.click()

    # ── Paso 6: Obtener URL de descarga ────────────────────────────────────
    time.sleep(2)
    print("    Buscando enlace de descarga...")
    enlace_guardar = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(SEL_BTN_GUARDAR)
    )
    url_descarga = enlace_guardar.get_attribute("href")
    print(f"    URL de descarga: {url_descarga}")

    # ── Paso 7: Descargar el PDF con las cookies de sesión ─────────────────
    nombre_limpio = nombre_trabajador.replace(" ", "_").upper()
    fecha_hoy     = date.today().isoformat()
    nombre_pdf    = f"CUL_{nombre_limpio}_{fecha_hoy}.pdf"
    ruta_pdf      = os.path.join(carpeta, nombre_pdf)

    descargado = False

    # Intento 1: urllib con cookies del browser
    try:
        cj     = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        ua     = driver.execute_script("return navigator.userAgent")

        for c in driver.get_cookies():
            ck = http.cookiejar.Cookie(
                version=0, name=c["name"], value=c["value"],
                port=None, port_specified=False,
                domain=c.get("domain", ""),
                domain_specified=bool(c.get("domain")),
                domain_initial_dot=c.get("domain", "").startswith("."),
                path=c.get("path", "/"), path_specified=bool(c.get("path")),
                secure=c.get("secure", False),
                expires=c.get("expiry"), discard=True,
                comment=None, comment_url=None, rest={}
            )
            cj.set_cookie(ck)

        opener.addheaders = [
            ("User-Agent", ua),
            ("Referer",    driver.current_url),
            ("Accept",     "application/pdf,*/*"),
        ]

        with opener.open(url_descarga, timeout=30) as resp:
            contenido = resp.read()

        if len(contenido) > 1000 and b"%PDF" in contenido[:10]:
            with open(ruta_pdf, "wb") as f:
                f.write(contenido)
            print(f"    ✅ PDF guardado: {ruta_pdf}")
            descargado = True
        else:
            print(f"    ⚠ Respuesta no es PDF ({len(contenido)} bytes)")

    except Exception as e:
        print(f"    ⚠ urllib falló: {e}")

    # Intento 2 (fallback): navegar con Chrome y esperar la descarga automática
    if not descargado:
        print("    Descargando via Chrome (fallback)...")
        driver.get(url_descarga)

        # Esperar hasta 30 segundos a que aparezca el PDF en la carpeta
        inicio = time.time()
        while time.time() - inicio < 30:
            pdfs         = list(Path(carpeta).glob("*.pdf"))
            en_progreso  = list(Path(carpeta).glob("*.crdownload"))
            if pdfs and not en_progreso:
                # Renombrar el primer PDF encontrado al nombre correcto
                pdfs[0].rename(ruta_pdf)
                print(f"    ✅ PDF guardado: {ruta_pdf}")
                descargado = True
                break
            time.sleep(1)

        if not descargado:
            print(f"    ❌ No se pudo descargar el PDF de {nombre_trabajador}")


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL POR TRABAJADOR
# ══════════════════════════════════════════════════════════════════════════════

def procesar_trabajador(nombre: str, dni: str, contrasena: str) -> bool:
    """
    Ejecuta el flujo completo para un trabajador:
    login → CAPTCHA → generar CUL → descargar PDF.
    Retorna True si todo fue exitoso, False si falló.
    """
    # Crear subcarpeta exclusiva para este trabajador
    nombre_limpio  = nombre.replace(" ", "_").upper()
    carpeta_worker = os.path.join(CARPETA_PDFS, nombre_limpio)
    Path(carpeta_worker).mkdir(parents=True, exist_ok=True)

    driver = crear_driver(carpeta_worker)
    wait   = WebDriverWait(driver, 15)

    try:
        # ── Abrir login ────────────────────────────────────────────────────
        driver.get(LOGIN_URL)
        time.sleep(2)

        seleccionar_tipo_dni(driver, wait)
        time.sleep(0.5)
        llenar_dni(wait, dni)
        time.sleep(0.5)
        llenar_contrasena(wait, contrasena)

        # ── Bucle de reintentos del CAPTCHA ────────────────────────────────
        login_exitoso = False

        for intento in range(1, MAX_INTENTOS_LOGIN + 1):
            print(f"    Intento {intento}/{MAX_INTENTOS_LOGIN}...")

            # Obtener un CAPTCHA válido (solo A-Z y 0-9)
            texto_captcha = None
            for _ in range(MAX_REFRESH_CAPTCHA):
                archivo = extraer_captcha(wait, carpeta_worker)
                texto   = leer_captcha_ocr(archivo)
                if re.fullmatch(r'[A-Z0-9]+', texto):
                    texto_captcha = texto
                    break
                print(f"    ⚠ CAPTCHA inválido '{texto}' — refrescando...")
                refrescar_captcha(wait)

            if not texto_captcha:
                print(f"    ❌ No se obtuvo CAPTCHA válido en {MAX_REFRESH_CAPTCHA} intentos.")
                continue

            print(f"    CAPTCHA leído: '{texto_captcha}'")
            llenar_campo_captcha(wait, texto_captcha)
            hacer_clic_acceder(wait)

            # Esperar popup de resultado (máx 5 segundos)
            try:
                titulo = cerrar_popup_swal(WebDriverWait(driver, 5))

                if "bienvenido" in titulo.lower():
                    print(f"    ✅ Login exitoso")
                    login_exitoso = True

                    # Cerrar modal de banner si aparece
                    time.sleep(2)
                    try:
                        cerrar_modal_banner(driver, WebDriverWait(driver, 10))
                    except Exception:
                        pass

                    # Ir al CUL y descargar
                    time.sleep(1)
                    click_obtener_certificado(driver, WebDriverWait(driver, 15))
                    time.sleep(2)
                    generar_y_descargar_cul(driver, WebDriverWait(driver, 15),
                                            nombre, carpeta_worker)
                    break

                else:
                    print(f"    ❌ Error en login: '{titulo}'")

            except Exception:
                print("    ❌ CAPTCHA incorrecto o sin popup de respuesta.")
                time.sleep(2)

        return login_exitoso

    except Exception as e:
        print(f"    ❌ Error inesperado: {e}")
        traceback.print_exc()
        return False

    finally:
        driver.quit()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("=" * 60)
    print("  CUL — Descarga automática de Certificados Únicos Laborales")
    print(f"  Fecha: {date.today().isoformat()}")
    print("=" * 60)
    print()

    # Crear carpeta raíz de PDFs
    Path(CARPETA_PDFS).mkdir(parents=True, exist_ok=True)

    # Obtener trabajadores de la BD
    try:
        trabajadores = obtener_trabajadores()
    except Exception as e:
        print(f"  ❌ No se pudo conectar a la base de datos: {e}")
        return

    if not trabajadores:
        print("  ❌ No hay trabajadores con DNI y Pass_cul en la BD.")
        return

    total    = len(trabajadores)
    exitosos = []
    fallidos = []

    for i, row in enumerate(trabajadores, start=1):
        nombre    = str(row[COL_APELLIDOS]).strip()
        dni       = str(row[COL_DNI]).strip()
        contrasena = str(row[COL_PASS]).strip()

        print(f"  [{i}/{total}] {nombre}  (DNI: {dni})")

        exito = procesar_trabajador(nombre, dni, contrasena)

        if exito:
            exitosos.append(nombre)
        else:
            fallidos.append(nombre)

        print()

        # Pausa entre trabajadores para no saturar el portal
        if i < total:
            print(f"  Esperando 5 segundos antes del siguiente...")
            print()
            time.sleep(5)

    # ── Resumen final ──────────────────────────────────────────────────────
    print("=" * 60)
    print("  RESUMEN FINAL")
    print(f"  ✅ Exitosos : {len(exitosos)}/{total}")
    print(f"  ❌ Fallidos : {len(fallidos)}")
    if fallidos:
        print()
        print("  Trabajadores con error:")
        for nombre in fallidos:
            print(f"    - {nombre}")
    print()
    print(f"  PDFs guardados en: {CARPETA_PDFS}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()