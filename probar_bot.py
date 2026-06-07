import sqlite3
from controlador import app

# Simulamos que somos Twilio enviando un mensaje al webhook del bot
def enviar_mensaje_simulado(texto_mensaje, telefono_usuario="+5491123456789"):
    # Creamos un cliente de prueba de Flask
    with app.test_client() as cliente:
        datos_formulario = {
            'Body': texto_mensaje,
            'From': telefono_usuario
        }
        # Enviamos el POST al webhook
        respuesta = cliente.post('/webhook', data=datos_formulario)
        
        # Limpiamos la respuesta de Twilio para leerla lindo en la terminal
        texto_limpio = respuesta.data.decode('utf-8')
        texto_limpio = texto_limpio.replace('<Response><Message>', '').replace('</Message></Response>', '')
        texto_limpio = texto_limpio.replace('<Response><Message><Body>', '').replace('</Body></Message></Response>', '')
        
        print(f"\n📱 USUARIO: {texto_mensaje}")
        print(f"🤖 BOT:\n{texto_limpio}")

# --- RECORRIDO DE PRUEBA SIMULADO ---
if __name__ == "__main__":
    print("=== INICIANDO PRUEBA LOCAL DEL BOT ===")
    
    # 1. El usuario saluda
    enviar_mensaje_simulado("Hola")
    
    # 2. El usuario elige la opción 1 (Psicólogo)
    input("\n[Presioná Enter para continuar el flujo...]")
    enviar_mensaje_simulado("1")
    
    # 3. El usuario ingresa su nombre
    input("\n[Presioná Enter para continuar el flujo...]")
    enviar_mensaje_simulado("Esteban Regg")
    
    # 4. El usuario elige el horario (Suponiendo que el ID de horario configurado sea 1)
    input("\n[Presioná Enter para continuar el flujo...]")
    enviar_mensaje_simulado("1")