from flask import Flask, request, render_template
from twilio.twiml.messaging_response import MessagingResponse
import sqlite3
from datetime import datetime
from flask_basicauth import BasicAuth
import re

app = Flask(__name__)
# Configuración de seguridad para el Panel Web
app.config['BASIC_AUTH_USERNAME'] = 'cic'       # Tu usuario para entrar
app.config['BASIC_AUTH_PASSWORD'] = 'medicos2026'   # Tu contraseña secreta
app.config['BASIC_AUTH_FORCE'] = False              # No forzar a todo el sitio (solo al panel)

basic_auth = BasicAuth(app)

def es_nombre_valido(nombre):
    # Quitamos espacios de los costados
    nombre = nombre.strip()
    
    # Regla 1: Que tenga al menos 3 caracteres
    if len(nombre) < 3:
        return False
        
    # Regla 2: Que tenga un máximo razonable (ej. 50 caracteres)
    if len(nombre) > 50:
        return False
        
    # Regla 3: Que solo contenga letras, espacios y acentos (no números ni símbolos raros)
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

    # Comandos globales de reinicio o saludo inicial
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

    # Obtenemos el estado y la memoria del usuario
    estado_actual, actividad_elegida, nombre_temporal = obtener_contexto_usuario(numero_usuario)
    print(f"[Estado Actual] {estado_actual} | Actividad Guardada ID: {actividad_elegida} | Nombre: {nombre_temporal}")

    # --- ESTADO INICIO: El usuario elige entre Sacar o Cancelar ---
    if estado_actual == "INICIO":
        if mensaje_recibido == "1":
            # Cambiamos al estado donde elige la especialidad
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
            # El usuario quiere cancelar. Buscamos si tiene turnos con su número de teléfono
            conn = conectar_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tr.id, a.nombre, tr.dia_semana, tr.hora 
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
                    reply += f"❌ Escribí el número *{t[0]}* para cancelar el turno de *{t[1]}* el día *{t[2]}* a las *{t[3]} hs.*\n"
                reply += "\nSi te equivocaste, podés escribir *Inicio* para volver al menú."
            else:
                reply = "No encontramos ningún turno activo asociado a tu número de teléfono. Escribí *Inicio* para volver al menú principal."
                actualizar_estado_usuario(numero_usuario, "INICIO")
        else:
            reply = "Por favor, elegí una opción válida escribiendo *1* (Sacar turno) o *2* (Cancelar turno)."
        
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    # --- NUEVO SUB-ESTADO: El usuario está eligiendo la especialidad para sacar turno ---
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

    # --- NUEVO FILTRO INTELIGENTE: Validar el formato del nombre ---
    elif estado_actual == "ESPERANDO_NOMBRE":
        nombre_usuario = mensaje_recibido.strip()
        
        # Validamos si el nombre cumple con las reglas (letras y longitud)
        if not es_nombre_valido(nombre_usuario):
            reply = "Por favor, ingresá un nombre y apellido válido (solo letras, sin números ni símbolos) para poder registrar tu turno."
            respuesta_twilio.message(reply)
            return str(respuesta_twilio)
            
        # Si el nombre es correcto, continúa guardando el estado
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
                reply += f"🔹 Escribí el número *{id_horario}* para el día *{dia}* a las *{hora} hs.*\n"
        else:
            reply = "Disculpame, por el momento no hay horarios configurados. Escribí *Inicio* para volver a empezar."
            actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    # --- ESTADO ELIGIO_HORARIO: Confirmación final del turno ---
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
                fecha_actual = datetime.now().strftime("%Y-%m-%d")
                
                cursor.execute("""
                    INSERT INTO turnos_reservados (cliente_nombre, cliente_telefono, actividad_id, dia_semana, hora, fecha_reserva)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nombre_temporal, numero_usuario, actividad_elegida, dia_semana, hora, fecha_actual))
                conn.commit()
                conn.close()
                
                # CORRECCIÓN AQUÍ: Usamos nombre_temporal que es el que tiene el nombre real guardado
                reply = f"¡Turno confirmado con éxito! 🎉\n\n📌 *Detalles:*\n• Paciente: {nombre_temporal}\n• Especialidad: {nombre_actividad}\n• Día: {dia_semana}\n• Hora: {hora} hs.\n\nEscribí *Inicio* para volver al menú principal."
                actualizar_estado_usuario(numero_usuario, "INICIO", actividad_id=0, nombre="")
            else:
                conn.close()
                reply = "El número de opción que ingresaste no corresponde a los turnos disponibles."
        else:
            reply = "Por favor, ingresá solo el número del turno."
            
        respuesta_twilio.message(reply)
        return str(respuesta_twilio)

    # --- ESTADO: PROCESAR LA CANCELACIÓN ---
    elif estado_actual == "ESPERANDO_CANCELACION":
        if mensaje_recibido.isdigit():
            id_turno_cancelar = int(mensaje_recibido)
            
            conn = conectar_db()
            cursor = conn.cursor()
            
            # Verificamos primero que ese ID de turno realmente le pertenezca a este número de teléfono
            cursor.execute("SELECT id FROM turnos_reservados WHERE id = ? AND cliente_telefono = ?", (id_turno_cancelar, numero_usuario))
            existe_turno = cursor.fetchone()
            
            if existe_turno:
                # Borramos el turno de la base de datos
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
    
    # Obtenemos la fecha de hoy en formato AAAA-MM-DD
    hoy = datetime.now().strftime("%Y-%m-%d")
    
    # Filtramos para traer solo turnos de hoy o del futuro (fecha_reserva >= hoy)
    cursor.execute("""
        SELECT tr.id, tr.cliente_nombre, tr.cliente_telefono, a.nombre, tr.dia_semana, tr.hora, tr.fecha_reserva
        FROM turnos_reservados tr
        JOIN actividades a ON tr.actividad_id = a.id
        WHERE tr.fecha_reserva >= ?
        ORDER BY tr.fecha_reserva ASC, tr.hora ASC
    """, (hoy,))
    
    todos_los_turnos = cursor.fetchall()
    conn.close()
    
    return render_template("panel.html", turnos=todos_los_turnos)

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