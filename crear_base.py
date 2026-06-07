import sqlite3

def inicializar_base_de_datos():
    conexion = sqlite3.connect('turnos_bot.db')
    cursor = conexion.cursor()

    # 1. TABLA DE ACTIVIDADES
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL
        )
    ''')

    # 2. TABLA DE HORARIOS DISPONIBLES (Configuración por actividad)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS horarios_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actividad_id INTEGER,
            dia_semana TEXT NOT NULL,
            hora TEXT NOT NULL,
            FOREIGN KEY (actividad_id) REFERENCES actividades(id)
        )
    ''')

    # 3. TABLA DE TURNOS RESERVADOS (Ahora incluye NOMBRE)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS turnos_reservados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nombre TEXT NOT NULL,
            cliente_telefono TEXT NOT NULL,
            actividad_id INTEGER,
            dia_semana TEXT NOT NULL,
            hora TEXT NOT NULL,
            fecha_reserva TEXT NOT NULL,
            FOREIGN KEY (actividad_id) REFERENCES actividades(id)
        )
    ''')

    # --- DATOS REALES DEL PROYECTO ---
    # Insertamos las dos actividades principales
    cursor.execute("INSERT INTO actividades (nombre) VALUES ('Psicólogo')")
    cursor.execute("INSERT INTO actividades (nombre) VALUES ('Pediatra')")

    # Supongamos que 'Psicólogo' tiene ID 1 y 'Pediatra' tiene ID 2
    # Cargamos horarios de prueba para Psicólogo (por ejemplo: Lunes y Miércoles por la tarde)
    cursor.execute("INSERT INTO horarios_config (actividad_id, dia_semana, hora) VALUES (1, 'Lunes', '16:00')")
    cursor.execute("INSERT INTO horarios_config (actividad_id, dia_semana, hora) VALUES (1, 'Lunes', '17:00')")
    cursor.execute("INSERT INTO horarios_config (actividad_id, dia_semana, hora) VALUES (1, 'Miércoles', '18:00')")
    
    # Cargamos horarios de prueba para Pediatra (por ejemplo: Martes y Jueves por la mañana)
    cursor.execute("INSERT INTO horarios_config (actividad_id, dia_semana, hora) VALUES (2, 'Martes', '09:00')")
    cursor.execute("INSERT INTO horarios_config (actividad_id, dia_semana, hora) VALUES (2, 'Martes', '10:00')")
    cursor.execute("INSERT INTO horarios_config (actividad_id, dia_semana, hora) VALUES (2, 'Jueves', '11:00')")

    conexion.commit()
    conexion.close()
    print("¡Base de datos recreada con éxito con el nuevo esquema!")

if __name__ == '__main__':
    inicializar_base_de_datos()