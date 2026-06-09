from flask import Flask, request, render_template
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
from datetime import datetime, timedelta
from flask_basicauth import BasicAuth
import re

app = Flask(__name__)
# Configuración de seguridad para el Panel Web
app.config['BASIC_AUTH_USERNAME'] = 'cic'       # Tu usuario para entrar
app.config['BASIC_AUTH_PASSWORD'] = 'medicos2026'   # Tu contraseña secreta
app.config['BASIC_AUTH_FORCE'] = False              # No forzar a todo el sitio (solo al panel)

basic_auth = BasicAuth(app)

# Diccionario para mapear los nombres de los días al número de la semana de Python (0=Lunes, 6=Domingo)
DIAS_MAPA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
}

def calcular_proxima_fecha(dia_semana_str):
    """Calcula la fecha exacta (YYYY-MM-DD) del próximo día de la semana indicado"""
    hoy = datetime.now()
    dia_objetivo = DIAS_MAPA.get(dia_semana_str.lower().strip())
    
    if dia_objetivo is None:
        return hoy.strftime("%Y-%m-%d")
        
    dias_de_diferencia = dia_objetivo - hoy.weekday()
    # Si el día ya pasó esta semana o es hoy, agendamos para la semana siguiente
    if dias_de_diferencia <= 0:
        dias_de_diferencia += 7
        
    fecha_destino = hoy + timedelta(days=dias_de_diferencia)
    return fecha_destino.strftime("%Y-%m-%d")

def es_nombre_valido(nombre):
    nombre = nombre.strip()
    if len(nombre) < 3 or len(nombre) > 50:
        return False
    patron = r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$"
    if not re.match(patron, nombre):
        return False
    return True

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje_recibido = request.form.get('Body', '').strip()
    numero_usuario = request.form.get('From', '')
    texto_limpio = mensaje_recibido.lower()
    
    print(f"\n[Mensaje Inbound] De: {numero_usuario} -> Texto: '{mensaje_recibido}'")
    
    respuesta_twilio = MessagingResponse()

    if texto_limpio in ["hola", "buen día", "buenas", "inicio", "reiniciar", "menú", "menu"]:
        actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
        
        reply = (
            "¡Hola! Bienvenido al sistema de turnos médicos. 🏥\n\n"
            "¿Qué te gustaría hacer hoy?\n\n"
            "Escribí *1* 👉 Sacar un turno nuevo\n"
            "Escribí *2* 👉 Cancelar un turno existente"
        )
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    estado_actual, actividad_elegida, nombre_temporal = obtener_contexto_usuario(numero_usuario)
    print(f"[Estado Actual] {estado_actual} | Actividad Guardada ID: {actividad_elegida} | Nombre: {nombre_temporal}")

    if estado_actual == "INICIO":
        if mensaje_recibido == "1":
            actualizar_estado_usuario(numero_usuario, "ELIGIENDO_ESPECIALIDAD")
            
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre FROM actividades")
            actividades = cursor.fetchall()
            conn.close()

            reply = "Perfecto. ¿Para qué especialidad te gustaría agendar?\n\n"
            for act in actividades:
                reply += f"👉 Escribí *{act[0]}* para *{act[1]}*\n"
            
        elif mensaje_recibido == "2":
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tr.id, a.nombre, tr.dia_semana, tr.fecha_reserva, tr.hora 
                FROM turnos_reservados tr
                JOIN actividades a ON tr.actividad_id = a.id
                WHERE tr.cliente_telefono = ?
            """, (numero_usuario,))
            turnos_usuario = cursor.fetchall()
            conn.close()

            if turnos_usuario:
                actualizar_estado_usuario(numero_usuario, "ESPERANDO_CANCELACION")
                reply = "Estos son tus turnos agendados asociados a este número de WhatsApp:\n\n"
                for t in turnos_usuario:
                    # Formateamos la fecha de YYYY-MM-DD a DD/MM para el mensaje de cancelación
                    fecha_dt = datetime.strptime(t[3], "%Y-%m-%d")
                    fecha_formateada = fecha_dt.strftime("%d/%m")
                    reply += f"❌ Escribí el número *{t[0]}* para cancelar el turno de *{t[1]}* el día *{t[2]} {fecha_formateada}* a las *{t[4]} hs.*\n"
                reply += "\nSi te equivocaste, podés escribir *Inicio* para volver al menú."
            else:
                reply = "No encontramos ningún turno activo asociado a tu número de teléfono. Escribí *Inicio* para volver al menú principal."
                actualizar_estado_usuario(numero_usuario, "INICIO")
        else:
            reply = "Por favor, elegí una opción válida escribiendo *1* (Sacar turno) o *2* (Cancelar turno)."
        
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    elif estado_actual == "ELIGIENDO_ESPECIALIDAD":
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM actividades")
        actividades = {str(act[0]): act[1] for act in cursor.fetchall()}
        conn.close()

        if mensaje_recibido in actividades:
            id_actividad = int(mensaje_recibido)
            nombre_actividad = actividades[mensaje_recibido]
            
            actualizar_estado_usuario(numero_usuario, "ESPERANDO_NOMBRE", actividad_id=id_actividad)
            reply = f"Perfecto, elegiste *{nombre_actividad}*.\n\nPor favor, ingresá tu **Nombre y Apellido** para registrar en el turno:"
        else:
            reply = "Por favor, elegí una opción válida escribiendo solo el número de la especialidad."
        
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    elif estado_actual == "ESPERANDO_NOMBRE":
        nombre_usuario = mensaje_recibido.strip()
        
        if not es_nombre_valido(nombre_usuario):
            reply = "Por favor, ingresá un nombre y apellido válido (solo letras, sin números ni símbolos) para poder registrar tu turno."
            respuesta_twilio.message(reply)
            return str(respuesta_twilio)
            
        actualizar_estado_usuario(numero_usuario, "ELIGIO_HORARIO", nombre=nombre_usuario)
        
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, dia_semana, hora FROM horarios_config WHERE actividad_id = ?", (actividad_elegida,))
        horarios_configurados = cursor.fetchall()
        conn.close()
        
        if horarios_configurados:
            reply = f"Muchas gracias {nombre_usuario}. Estos son los turnos disponibles:\n\n"
            for hor in horarios_configurados:
                id_horario, dia, hora = hor
                # Calculamos dinámicamente la fecha (DD/MM) para mostrársela al usuario
                fecha_calculada_str = calcular_proxima_fecha(dia)
                fecha_dt = datetime.strptime(fecha_calculada_str, "%Y-%m-%d")
                fecha_formateada = fecha_dt.strftime("%d/%m")
                
                reply += f"🔹 Escribí el número *{id_horario}* para el día *{dia} {fecha_formateada}* a las *{hora} hs.*\n"
        else:
            reply = "Disculpame, por el momento no hay horarios configurados. Escribí *Inicio* para volver a empezar."
            actualizar_estado_usuario(numero_usuario, "INICIO")
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    elif estado_actual == "ELIGIO_HORARIO":
        if mensaje_recibido.isdigit():
            id_horario_elegido = int(mensaje_recibido)
            
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hc.dia_semana, hc.hora, a.nombre 
                FROM horarios_config hc 
                JOIN actividades a ON hc.actividad_id = a.id 
                WHERE hc.id = ? AND hc.actividad_id = ?
            """, (id_horario_elegido, actividad_elegida))
            horario_data = cursor.fetchone()
            
            if horario_data:
                dia_semana, hora, nombre_actividad = horario_data
                
                # Calculamos la fecha exacta del turno para guardarla de forma precisa en la DB
                fecha_turno = calcular_proxima_fecha(dia_semana)
                fecha_dt = datetime.strptime(fecha_turno, "%Y-%m-%d")
                fecha_formateada = fecha_dt.strftime("%d/%m/%y")
                
                cursor.execute("""
                    INSERT INTO turnos_reservados (cliente_nombre, cliente_telefono, actividad_id, dia_semana, hora, fecha_reserva)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nombre_temporal, numero_usuario, actividad_elegida, dia_semana, hora, fecha_turno))
                conn.commit()
                conn.close()
                
                reply = f"¡Turno confirmado con éxito! 🎉\n\n📌 *Detalles:*\n• Paciente: {nombre_temporal}\n• Especialidad: {nombre_actividad}\n• Día: {dia_semana} {fecha_formateada}\n• Hora: {hora} hs.\n\nEscribí *Inicio* para volver al menú principal."
                actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
            else:
                conn.close()
                reply = "El número de opción que ingresaste no corresponde a los turnos disponibles."
        else:
            reply = "Por favor, ingresá solo el número del turno."
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    elif estado_actual == "ESPERANDO_CANCELACION":
        if mensaje_recibido.isdigit():
            id_turno_cancelar = int(mensaje_recibido)
            
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM turnos_reservados WHERE id = ? AND cliente_telefono = ?", (id_turno_cancelar, numero_usuario))
            existe_turno = cursor.fetchone()
            
            if existe_turno:
                cursor.execute("DELETE FROM turnos_reservados WHERE id = ?", (id_turno_cancelar,))
                conn.commit()
                conn.close()
                
                reply = "¡Tu turno ha sido cancelado con éxito! ❌ El horario ya quedó liberado para otro paciente. Si necesitás algo más, escribí *Inicio*."
                actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
            else:
                conn.close()
                reply = "El ID ingresado no corresponde a ninguno de tus turnos activos. Por favor, revisá el número de la lista de arriba."
        else:
            reply = "Por favor, ingresá solo el número identificador del turno que deseas cancelar."
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    return str(respuesta_twilio)

@app.route("/panel", methods=["GET"])
@basic_auth.required
def ver_panel():
    conn = conectar_db()
    cursor = conn.cursor()
    hoy = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT tr.id, tr.cliente_nombre, tr.cliente_telefono, a.nombre, tr.dia_semana, tr.hora, tr.fecha_reserva
        FROM turnos_reservados tr
        JOIN actividades a ON tr.actividad_id = a.id
        WHERE tr.fecha_reserva >= ?
        ORDER BY tr.fecha_reserva ASC, tr.hora ASC
    """, (hoy,))
    
    todos_los_turnos = cursor.fetchall()
    conn.close()
    
    # Procesamos los turnos para cambiar el formato de fecha de 'YYYY-MM-DD' a 'DD/MM' antes de mandarlo al HTML
    turnos_procesados = []
    for t in todos_los_turnos:
        fecha_dt = datetime.strptime(t[6], "%Y-%m-%d")
        fecha_corta = fecha_dt.strftime("%d/%m/%y")
        
        turno_dict = {
            "id": t[0],
            "cliente_nombre": t[1],
            "cliente_telefono": t[2],
            "actividad_nombre": t[3],
            "dia_semana": t[4],
            "hora": t[5],
            "fecha": fecha_corta
        }
        turnos_procesados.append(turno_dict)
    
    return render_template("panel.html", turnos=turnos_procesados)

def conectar_db():
    return sqlite3.connect("turnos_bot.db")

def obtener_contexto_usuario(telefono):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estados_usuario (
            telefono TEXT PRIMARY KEY,
            estado TEXT,
            actividad_id INTEGER,
            nombre_temporal TEXT
        )
    """)
    cursor.execute("SELECT estado, actividad_id, nombre_temporal FROM estados_usuario WHERE telefono = ?", (telefono,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado:
        return resultado[0], resultado[1], resultado[2]
    else:
        return "INICIO", 0, ""

def actualizar_estado_usuario(telefono, nuevo_estado, actividad_id=None, nombre=None):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estados_usuario (
            telefono TEXT PRIMARY KEY,
            estado TEXT,
            actividad_id INTEGER,
            nombre_temporal TEXT
        )
    """)
    cursor.execute("SELECT actividad_id, nombre_temporal FROM estados_usuario WHERE telefono = ?", (telefono,))
    existente = cursor.fetchone()
    
    act_id = actividad_id if actividad_id is not None else (existente[0] if existente else 0)
    nom_temp = nombre if nombre is not None else (existente[1] if existente else "")
    
    cursor.execute("""
        INSERT INTO estados_usuario (telefono, estado, actividad_id, nombre_temporal)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telefono) DO UPDATE SET
            estado = excluded.estado,
            actividad_id = excluded.actividad_id,
            nombre_temporal = excluded.nombre_temporal
    """, (telefono, nuevo_estado, act_id, nom_temp))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)