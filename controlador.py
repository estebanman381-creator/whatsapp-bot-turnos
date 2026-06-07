from flask import Flask, request, render_template
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
from datetime import datetime

app = Flask(__name__)

def conectar_db():
    conn = sqlite3.connect("turnos_bot.db")
    cursor = conn.cursor()
    
    # Aseguramos que exista la tabla de estados con columnas para recordar la selección
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estados_usuarios (
            telefono TEXT PRIMARY KEY,
            estado_actual TEXT NOT NULL,
            actividad_elegida INTEGER,
            nombre_temporal TEXT
        )
    ''')
    conn.commit()
    return conn

def obtener_contexto_usuario(telefono):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT estado_actual, actividad_elegida, nombre_temporal FROM estados_usuarios WHERE telefono = ?", (telefono,))
    resultado = cursor.fetchone()
    conn.close()
    if resultado:
        return resultado[0], resultado[1], resultado[2]
    return "INICIO", None, None

def actualizar_estado_usuario(telefono, nuevo_estado, actividad_id=None, nombre=None):
    conn = conectar_db()
    cursor = conn.cursor()
    
    # Si pasamos None en los datos nuevos, intentamos mantener lo que ya estaba para no borrar la memoria
    estado_act, act_id_act, nom_act = obtener_contexto_usuario(telefono)
    
    final_actividad = actividad_id if actividad_id is not None else act_id_act
    final_nombre = nombre if nombre is not None else nom_act

    cursor.execute("""
        INSERT INTO estados_usuarios (telefono, estado_actual, actividad_elegida, nombre_temporal) 
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telefono) DO UPDATE SET 
            estado_actual = excluded.estado_actual,
            actividad_elegida = excluded.actividad_elegida,
            nombre_temporal = excluded.nombre_temporal
    """, (telefono, nuevo_estado, final_actividad, final_nombre))
    conn.commit()
    conn.close()

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje_recibido = request.form.get('Body', '').strip()
    numero_usuario = request.form.get('From', '')
    texto_limpio = mensaje_recibido.lower()
    
    print(f"\n[Mensaje Inbound] De: {numero_usuario} -> Texto: '{mensaje_recibido}'")
    
    respuesta_twilio = MessagingResponse()

    # Comandos globales de reinicio
    if texto_limpio in ["hola", "buen día", "buenas", "inicio", "reiniciar"]:
        actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
        
        # Consultamos las actividades disponibles en la DB
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM actividades")
        actividades = cursor.fetchall()
        conn.close()

        reply = "¡Hola! Bienvenido al sistema de turnos. 🏥\n\n¿Para qué especialidad te gustaría agendar un turno?\n\n"
        for act in actividades:
            reply += f"👉 Escribí *{act[0]}* para *{act[1]}*\n"
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    # Obtenemos el estado y la memoria del usuario
    estado_actual, actividad_elegida, nombre_temporal = obtener_contexto_usuario(numero_usuario)
    print(f"[Estado Actual] {estado_actual} | Actividad Guardada ID: {actividad_elegida} | Nombre: {nombre_temporal}")

    # --- ESTADO INICIO: El usuario elige la especialidad ---
    if estado_actual == "INICIO":
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM actividades")
        actividades = {str(act[0]): act[1] for act in cursor.fetchall()}
        conn.close()

        if mensaje_recibido in actividades:
            id_actividad = int(mensaje_recibido)
            nombre_actividad = actividades[mensaje_recibido]
            
            # Guardamos la actividad elegida y pasamos a pedir el nombre
            actualizar_estado_usuario(numero_usuario, "ESPERANDO_NOMBRE", actividad_id=id_actividad)
            
            reply = f"Perfecto, elegiste *{nombre_actividad}*.\n\nPor favor, ingresá tu **Nombre y Apellido** para registrar en el turno:"
        else:
            reply = "Por favor, elegí una opción válida escribiendo solo el número de la especialidad."
        
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    # --- ESTADO ESPERANDO_NOMBRE: El usuario ingresa su nombre ---
    elif estado_actual == "ESPERANDO_NOMBRE":
        if len(mensaje_recibido) > 2: # Validación simple de que no sea un texto vacío o un solo caracter
            nombre_usuario = mensaje_recibido
            
            # Guardamos el nombre en la memoria intermedia y avanzamos a mostrar horarios
            actualizar_estado_usuario(numero_usuario, "ELIGIO_HORARIO", nombre=nombre_usuario)
            
            # Buscamos los horarios configurados para ESTA actividad
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, dia_semana, hora FROM horarios_config WHERE actividad_id = ?", (actividad_elegida,))
            horarios_configurados = cursor.fetchall()
            conn.close()
            
            if horarios_configurados:
                reply = f"Muchas gracias {nombre_usuario}. Estos son los turnos disponibles para la especialidad seleccionada:\n\n"
                for hor in horarios_configurados:
                    id_horario, dia, hora = hor
                    reply += f"🔹 Escribí el número *{id_horario}* para el día *{dia}* a las *{hora} hs.*\n"
            else:
                reply = "Disculpame, por el momento no hay horarios configurados para esta especialidad. Escribí *Inicio* para volver a empezar."
                actualizar_estado_usuario(numero_usuario, "INICIO")
        else:
            reply = "Por favor, ingresá un nombre y apellido válido."
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    # --- ESTADO ELIGIO_HORARIO: El usuario selecciona el turno final ---
    elif estado_actual == "ELIGIO_HORARIO":
        if mensaje_recibido.isdigit():
            id_horario_elegido = int(mensaje_recibido)
            
            conn = conectar_db()
            cursor = conn.cursor()
            
            # Verificamos que el ID de horario corresponda a la actividad
            cursor.execute("""
                SELECT hc.dia_semana, hc.hora, a.nombre 
                FROM horarios_config hc 
                JOIN actividades a ON hc.actividad_id = a.id 
                WHERE hc.id = ? AND hc.actividad_id = ?
            """, (id_horario_elegido, actividad_elegida))
            
            horario_data = cursor.fetchone()
            
            if horario_data:
                dia_semana, hora, nombre_actividad = horario_data
                fecha_actual = datetime.now().strftime("%Y-%m-%d") # Fecha de registro
                
                # Insertamos la reserva formal en la tabla turnos_reservados
                cursor.execute("""
                    INSERT INTO turnos_reservados (cliente_nombre, cliente_telefono, actividad_id, dia_semana, hora, fecha_reserva)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nombre_temporal, numero_usuario, actividad_elegida, dia_semana, hora, fecha_actual))
                
                conn.commit()
                conn.close()
                
                reply = (
                    f"¡Turno confirmado con éxito! 🎉\n\n"
                    f"📌 *Detalles del Turno:*\n"
                    f"• Paciente: {nombre_temporal}\n"
                    f"• Especialidad: {nombre_actividad}\n"
                    f"• Día: {dia_semana}\n"
                    f"• Hora: {hora} hs.\n\n"
                    f"¡Muchas gracias! Si necesitás gestionar otro turno, escribí *Inicio*."
                )
                # Reseteamos el estado del usuario al finalizar con éxito
                actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
            else:
                conn.close()
                reply = "El número de opción que ingresaste no corresponde a los turnos disponibles. Por favor, revisá la lista de arriba."
        else:
            reply = "Entrada inválida. Por favor, ingresá solo el *número* del turno que querés reservar."
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    return str(respuesta_twilio)
@app.route("/panel", methods=["GET"])
def ver_panel():
    conn = conectar_db()
    cursor = conn.cursor()
    
    # Hacemos una consulta cruzada (JOIN) para traer el nombre real de la actividad en lugar del ID numérico
    cursor.execute("""
        SELECT tr.id, tr.cliente_nombre, tr.cliente_telefono, a.nombre, tr.dia_semana, tr.hora, tr.fecha_reserva
        FROM turnos_reservados tr
        JOIN actividades a ON tr.actividad_id = a.id
        ORDER BY tr.id DESC
    """)
    
    todos_los_turnos = cursor.fetchall()
    conn.close()
    
    # Le pasamos los datos al archivo HTML para que los dibuje en la pantalla
    return render_template("panel.html", turnos=todos_los_turnos)
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)