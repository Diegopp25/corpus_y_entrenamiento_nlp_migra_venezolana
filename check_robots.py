import urllib.robotparser


def chekear_robots(url_robot, url_target):
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(url_robot)
    rp.read()

    url = url_target

    print(rp.can_fetch("*", url))


print("EC:")
chekear_robots("https://www.elespectador.com/robots.txt", "https://www.elespectador.com/buscador/migraci%C3%B3n-venezolana")
print("MM:")
chekear_robots("https://www.milenio.com/robots.txt", "https://www.milenio.com/buscador?")
print("HM:")
chekear_robots("https://heraldodemexico.com.mx/robots.txt", "https://heraldodemexico.com.mx/noticias/buscar/?buscar=migraci%C3%B3n+venezolana")
print("HC:")
chekear_robots("https://www.elheraldo.co/robots.txt", "https://www.elheraldo.co/buscador/?query=migraci%C3%B3n%20venezolana")
print("Semana:")
chekear_robots("https://www.semana.com/robots.txt", "https://www.semana.com")

chekear_robots("https://archiveofourown.org/robots.txt", "https://archiveofourown.org")

