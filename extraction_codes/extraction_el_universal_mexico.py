from selenium import webdriver
from selenium. webdriver.chrome.options import Options
from selenium. webdriver.common.by import By
import pandas as pd
import time
import re


from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import requests
import json


# ==========================
# CONFIGURACIÓN
# ==========================
options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-notifications")
driver = webdriver.Chrome(options=options)

url = "https://www.eluniversal.com.mx/buscador/?query=migraci%C3%B3n+venezolana"
driver.get(url)

print("⏳ Esperando carga inicial...")
time.sleep(10)


def extraction():

    print("\n" + "=" * 70)
    print("EL UNIVERSAL - MIGRACIÓN VENEZOLANA")
    print("=" * 70)

    # ==========================
    # CARGAR MÁS RESULTADOS
    # ==========================

    for _ in range(10):

        try:

            boton = driver.find_element(
                By.XPATH,
                "//*[contains(text(),'Mostrar más')]"
            )

            driver.execute_script(
                "arguments[0].click();",
                boton
            )

            time.sleep(3)

        except:
            break

    # ==========================
    # OBTENER ENLACES
    # ==========================

    print("🔍 Buscando artículos...")

    try:

        resultados = driver.find_element(
            By.ID,
            "resultdata"
        )

        enlaces = resultados.find_elements(
            By.TAG_NAME,
            "a"
        )

    except:

        enlaces = driver.find_elements(
            By.TAG_NAME,
            "a"
        )

    urls = set()

    for enlace in enlaces:

        try:

            href = enlace.get_attribute("href")

            texto = enlace.text.strip()

            if not href:
                continue

            if "eluniversal.com.mx" not in href:
                continue

            if "/buscador/" in href:
                continue

            if len(texto) < 15:
                continue

            urls.add(href)

        except:
            continue

    urls = list(urls)

    print(f"✅ URLs encontradas: {len(urls)}")

    # ==========================
    # LISTAS
    # ==========================

    titulos = []
    categorias = []
    autores = []
    fechas = []
    cuerpos = []
    links = []

    # ==========================
    # RECORRER ARTÍCULOS
    # ==========================

    for i, url in enumerate(urls, start=1):

        print(f"\n[{i}/{len(urls)}]")
        print(url)

        try:

            driver.get(url)

            time.sleep(3)

            # ------------------
            # TÍTULO
            # ------------------

            try:
                titulo = driver.find_element(
                    By.CSS_SELECTOR,
                    'meta[property="og:title"]'
                ).get_attribute("content")
            except:
                titulo = ""

            # ------------------
            # CATEGORÍA
            # ------------------

            try:
                categoria = driver.find_element(
                    By.CSS_SELECTOR,
                    'meta[name="category"]'
                ).get_attribute("content")
            except:
                categoria = ""

            # ------------------
            # AUTOR
            # ------------------

            try:
                autor = driver.find_element(
                    By.CSS_SELECTOR,
                    'meta[property="autor"]'
                ).get_attribute("content")
            except:
                autor = ""

            # ------------------
            # FECHA
            # ------------------

            try:
                fecha = driver.find_element(
                    By.CSS_SELECTOR,
                    'meta[name="fecha_publicacion"]'
                ).get_attribute("content")
            except:
                fecha = ""

            # ------------------
            # CUERPO
            # ------------------

            parrafos = driver.find_elements(
                By.CSS_SELECTOR,
                "article p"
            )

            if not parrafos:

                parrafos = driver.find_elements(
                    By.TAG_NAME,
                    "p"
                )

            cuerpo = " ".join(

                p.text.strip()

                for p in parrafos

                if len(p.text.strip()) > 40

            )

            titulos.append(titulo)
            categorias.append(categoria)
            autores.append(autor)
            fechas.append(fecha)
            cuerpos.append(cuerpo)
            links.append(url)

        except Exception as e:

            print(f"❌ Error: {e}")

    # ==========================
    # DATAFRAME
    # ==========================

    df = pd.DataFrame({

        "Titulo": titulos,
        "Categoria": categorias,
        "Autor": autores,
        "Fecha": fechas,
        "URL": links,
        "Cuerpo": cuerpos

    })

    # ==========================
    # LIMPIEZA
    # ==========================

    df = df[
        df["Categoria"].notna()
    ]

    df = df[
        df["Categoria"].astype(str).str.strip() != ""
    ]

    df = df.drop_duplicates(
        subset=["URL"]
    )

    print("\n✅ Registros finales:", len(df))

    return df

# ============================================
# EJECUCIÓN
# ============================================

df = extraction()

print(df.head())

#driver.quit()