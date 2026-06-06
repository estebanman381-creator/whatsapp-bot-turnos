import sqlite3

def inicializar_sistema():
    # Conectamos a la base de datos (si no existe, Python la crea automáticamente)
    conexion = sqlite3.connect("turnos_bot.db")
    cursor = conexion.cursor()
    
    # 1. Creamos la tabla de Turnos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actividad TEXT NOT NULL,
        fecha TEXT NOT NULL,
        hora TEXT NOT NULL,
        cliente_telefono TEXT
    )
    """)
    
    # 2. Creamos la tabla para recordar el estado de cada usuario
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS estados_usuarios (
        telefono TEXT PRIMARY KEY,
        estado_actual TEXT NOT NULL
    )
    """)
    
    # 3. Limpiamos turnos de prueba viejos (para no duplicar si corremos el script de nuevo)
    cursor.execute("DELETE FROM turnos")
    
    # 4. Cargamos algunos turnos libres de prueba (cliente_telefono queda en None/NULL)
    turnos_iniciales = [
        # Actividad, Fecha, Hora, Telefono del cliente (None = Libre)
        ('Psicologo', '2026-06-10', '15:00', None),
        ('Psicologo', '2026-06-10', '16:30', None),
        ('Psicologo', '2026-06-11', '09:00', None),
        ('Pediatra', '2026-06-10', '10:00', None),
        ('Pediatra', '2026-06-11', '11:30', None),
        ('Pediatra', '2026-06-11', '12:15', None)
    ]
    
    cursor.executemany("""
        INSERT INTO turnos (actividad, fecha, hora, cliente_telefono) 
        VALUES (?, ?, ?, ?)
    """, turnos_iniciales)
    
    conexion.commit()
    conexion.close()
    print("¡Base de datos 'turnos_bot.db' creada y cargada con turnos de prueba con éxito!")

if __name__ == "__main__":
    inicializar_sistema()