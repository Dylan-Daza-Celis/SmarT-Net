"""Crear el primer administrador usando entrada interactiva, sin contraseña en argv."""
from getpass import getpass
from sqlalchemy import select, func
from .database import Session
from .models import User
from .security import password_hasher

def main():
    username = input("Usuario administrador: ").strip()
    password = getpass("Contraseña (mínimo 12 caracteres): ")
    if not username or len(username) > 100 or len(password) < 12 or len(password) > 128:
        raise SystemExit("Usuario o contraseña inválidos")
    with Session.begin() as db:
        # Serializa bootstrap concurrente en PostgreSQL.
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy import text
            db.execute(text("LOCK TABLE users IN EXCLUSIVE MODE"))
        if db.scalar(select(func.count()).select_from(User)):
            raise SystemExit("Ya existen usuarios; utilice la API de administración")
        db.add(User(username=username, password_hash=password_hasher.hash(password), role="administrador"))
    print("Administrador creado")

if __name__ == "__main__":
    main()
