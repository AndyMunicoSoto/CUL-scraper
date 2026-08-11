from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import os
import re
import time
import easyocr

OCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)

ruta_del_codigo = os.path.dirname(os.path.abspath(__file__))
carpeta = os.path.join(ruta_del_codigo, "imagenes_captcha")
os.makedirs(carpeta, exist_ok=True)

def crear_driver():

    options = webdriver.ChromeOptions() # Agregado recientemente
    prefs = {
            "download.default_directory": r"C:\\Users\\Andy M\\Documents\\optimizacion\\CUL_V2\\CUL-scraper\\CULs",  # carpeta deseada
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,  # descarga en lugar de abrir
        }
    options.add_experimental_option("prefs", prefs)


    driver = webdriver.Chrome(options=options) # Agregado recientemente
    driver.maximize_window()
    driver.get("https://www.empleosperu.gob.pe/portal-mtpe/#/login")

    return driver

def login(driver, dni, contrasena):
    # # Esperamos a que el campo de DNI esté presente
    # WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "sNumeroDocumentoIdentidad")))
    
    # # Ingresamos el DNI y la contraseña
    # campo_DNI = driver.find_element(By.ID, "sNumeroDocumentoIdentidad")
    # campo_DNI.send_keys(dni)

    campo_select_DNI = driver.find_element(By.ID, "cboTipoDocumento")
    select = Select(campo_select_DNI)
    select.select_by_visible_text("DNI")  # Seleccionamos la opción "DNI" del select

    campo_DNI = driver.find_element(By.ID, "sNumeroDocumentoIdentidad")
    campo_DNI.send_keys(dni)

    campo_contrasena = driver.find_element(By.ID, "password")
    campo_contrasena.send_keys(contrasena)

def tipo_alerta(driver) -> str:
    alerta = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "swal2-title")))
    alerta_texto = alerta.text
    print("Texto de la alerta:", alerta_texto)
    return alerta_texto
    # ¡Bienvenido!
    # ¡Alerta!
    
def solve_captcha(driver):
    SEL_CAPTCHA_IMG   = (By.CSS_SELECTOR, "img[src^='blob:']")
    img_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located(SEL_CAPTCHA_IMG))
    ruta = os.path.join(carpeta, "captcha.png")
    img_element.screenshot(ruta)
    return ruta

def leer_captcha(ruta):
    resultados = OCR_READER.readtext(ruta, detail=0)
    texto = resultados[0].replace(" ", "").strip().upper()
    print("Resultado OCR:", texto)
    return texto

def ingresar_captcha(driver, texto):
    campo_captcha = driver.find_element(By.ID, "captcha")
    campo_captcha.send_keys(texto)

    btn_ingresar = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    btn_ingresar.click()

    time.sleep(5)  # Esperamos un segundo antes de hacer clic en el botón de inicio de sesión

def bienvenida(driver):
   
    # Esperamos a que el mensaje de bienvenida esté presente
    mensaje_bienvenida = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.swal2-confirm")))
    #print("Mensaje de bienvenida:", mensaje_bienvenida.text)
    mensaje_bienvenida.click()
    time.sleep(2)  # Esperamos un segundo antes de continuar
   
def bienvenida_2(driver):
    btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.modal-footer button.btn-danger")))
    btn.click()

    time.sleep(5)  # Esperamos un segundo antes de continuar


def obtener_certificado(driver):

    btn_certi = WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Obtener Certificado')]")))
    btn_certi.click()
    time.sleep(5)  # Esperamos un segundo antes de continuar

def solicitar_certificado(driver):
    btn_solicitar = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "solicitar")))
    btn_solicitar.click()
    time.sleep(5)  # Esperamos un segundo antes de continuar

def descargar_certificado(driver):
    # Esperamos a que el botón de descarga esté presente
    link_guardar = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Guardar') and contains(@href, 'DescargarCUL')]"))
    )
    link_guardar.click()
    time.sleep(5)  # Esperamos un segundo antes de continuar

def carpeta_certificados(driver):

    btn_carpe = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(.,'Ver mi carpeta de certificados')]")))
    btn_carpe.click()
    time.sleep(5)  # Esperamos un segundo antes de continuar

def ver_certificados(driver):

    btn_carpe = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(.,' Ver Certificado')]")))
    btn_carpe.click()
    time.sleep(5)  # Esperamos un segundo antes de continuar

def pasar_cul_descarga(driver):
    try:
        btn_generar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "solicitar"))
        )
        time.sleep(3)
        btn_generar.click()

        print("Se hizo clic en 'Generar Certificado Único Laboral'")

    except TimeoutException:

        print("Botón 'Generar' no disponible. Usando historial...")

        # btn_historial = WebDriverWait(driver, 10).until(
        #     EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Ver mi carpeta de certificados')]"))
        # )
        # time.sleep(3)
        # btn_historial.click()
        carpeta_certificados(driver)
        ver_certificados(driver)

def cerrar_sesion(driver):

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'Salir.html') and contains(., 'Cerrar sesión')]"))
    ).click()
    
    # WebDriverWait(driver, 10).until(
    #     EC.presence_of_element_located((By.NAME, "dni"))
    # )

def finalizar_usuario(driver):
    try:
        cerrar_sesion(driver)
    except:
        pass
    finally:
        driver.quit()

def main():

    usuarios = [
        ("48508068", "Porlasara1@"),
        ("71251100", "zmaxwtf123"), #ENZO
        ("72378883", "Fortuito147=") # DANIEL
    ]

    for dni, contrasena in usuarios:

        validacion = True

        #crear_driver()
        driver = crear_driver()

        while validacion:
            
            driver.refresh()
            ## AUTOMATIZAR
            login(driver, dni, contrasena)
            ruta = solve_captcha(driver)
            texto = leer_captcha(ruta)
            time.sleep(2)  # Esperamos un segundo antes de ingresar el captcha
            ingresar_captcha(driver, texto)
            alerta = tipo_alerta(driver)

            if alerta == "¡Bienvenido!":
                validacion = False

        bienvenida(driver)
        bienvenida_2(driver)
        obtener_certificado(driver)

        pasar_cul_descarga(driver)

        descargar_certificado(driver)

        finalizar_usuario(driver)

if __name__ == "__main__":
    main()