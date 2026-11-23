import urllib.robotparser


def chekear_robots(url_robot, url_target):
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(url_robot)
    rp.read()

    url = url_target

    print(rp.can_fetch("*", url))


print("El Espectador:")
chekear_robots("https://www.elespectador.com/robots.txt", "https://www.elespectador.com/buscador/migraci%C3%B3n-venezolana")
print("Milenio:")
chekear_robots("https://www.milenio.com/robots.txt", "https://www.milenio.com/buscador?")
print("Heraldo de Mexico:")
chekear_robots("https://heraldodemexico.com.mx/robots.txt", "https://heraldodemexico.com.mx/noticias/buscar/?buscar=migraci%C3%B3n+venezolana")
print("El Heraldo:")
chekear_robots("https://www.elheraldo.co/robots.txt", "https://www.elheraldo.co/buscador/?query=migraci%C3%B3n%20venezolana")
print("Semana:")
chekear_robots("https://www.semana.com/robots.txt", "https://www.semana.com")
print("Reforma:")
chekear_robots("https://www.reforma.com/robots.txt", "https://busquedas.reforma.com/buscar/reforma/pages/default.aspx")
print("El Sol de México:")
chekear_robots("https://oem.com.mx/robots.txt", "https://oem.com.mx")
print("La Jornada:")
chekear_robots("https://www.jornada.com.mx/robots.txt", "https://www.jornada.com.mx")
print("La Crónica:")
chekear_robots("https://www.cronica.com.mx/robots.txt", "https://www.cronica.com.mx") #promising