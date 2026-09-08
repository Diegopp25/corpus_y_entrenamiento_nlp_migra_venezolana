import re


def limpiar_cuerpo_espectador(texto: str) -> str:

    """
    Limpia texto extraído por web scraping, corrigiendo problemas comunes:
    - Etiquetas HTML sueltas o mal cerradas (ej: '<a')
    - Saltos de línea \\r\\n mezclados o duplicados
    - Espacios múltiples
    - Espacios insertados dentro de palabras (ej: 'labora l' -> 'laboral')
    - Backslashes sueltos que rompen oraciones
    - Espacios antes de signos de puntuación
    """

    # 1. Eliminar etiquetas/fragmentos HTML sueltos (ej: '<a', '<div', etc.)
    texto = re.sub(r'<[^>]*>?', ' ', texto)
    texto = re.sub(r'<[a-zA-Z]+\b', ' ', texto)  # tags sin cerrar tipo '<a'

    # 2. Normalizar saltos de línea (\r\n, \r, \n) a un solo espacio
    texto = texto.replace('\r\n', '\n')
    texto = re.sub(r'\n+', '\n', texto)
    texto = re.sub(r'\n', ' ', texto)

    # 3. Eliminar backslashes sueltos (residuos de escapado mal hecho)
    texto = re.sub(r'\s*\\\s*', ' ', texto)

    # 4. Corregir espacios insertados dentro de palabras conocidas
    #    (patrón general: letra + espacio + 1 letra sola pegada a otra palabra)
    #    Aquí se corrige el caso puntual detectado: "labora l" -> "laboral"
    correcciones_puntuales = {
        r'\blabora\s+l\b': 'laboral',
    }
    for patron, reemplazo in correcciones_puntuales.items():
        texto = re.sub(patron, reemplazo, texto)

    # 5. Colapsar espacios múltiples en uno solo
    texto = re.sub(r'[ \t]+', ' ', texto)

    # 6. Quitar espacios antes de signos de puntuación
    texto = re.sub(r'\s+([.,;:%])', r'\1', texto)

    # 7. Quitar espacios pegados a comillas curvas “ ”
    texto = re.sub(r'“\s+', '“', texto)
    texto = re.sub(r'\s+”', '”', texto)

    # 8. Eliminar espacios al inicio/final
    texto = texto.strip()

    return texto


