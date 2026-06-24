def get_base_template(content: str):
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #ebe7f3;
                margin: 0;
                padding: 0;
                color: #1a1a2e;
            }}
            .container {{
                max-width: 600px;
                margin: 20px auto;
                background-color: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(52, 33, 107, 0.1);
            }}
            .header {{
                background-color: #34216b;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                color: #ffffff;
                margin: 0;
                font-size: 28px;
                letter-spacing: 1px;
            }}
            .content {{
                padding: 40px;
                line-height: 1.6;
            }}
            .footer {{
                background-color: #f5f3f9;
                padding: 20px;
                text-align: center;
                font-size: 12px;
                color: #6b6b80;
            }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #34216b;
                color: #ffffff !important;
                text-decoration: none;
                border-radius: 8px;
                font-weight: bold;
                margin-top: 20px;
            }}
            .status-badge {{
                display: inline-block;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                margin-bottom: 20px;
            }}
            .status-error {{
                background-color: #fee2e2;
                color: #e74c3c;
            }}
            .status-success {{
                background-color: #dcfce7;
                color: #27ae60;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MiCasita</h1>
            </div>
            <div class="content">
                {content}
            </div>
            <div class="footer">
                &copy; 2026 MiCasita. Tu hogar, tu comunidad.<br>
                Este es un mensaje automático, por favor no respondas a este correo.
            </div>
        </div>
    </body>
    </html>
    """

def get_block_notification_template(user_name: str, is_active: bool):
    status_text = "Activa" if is_active else "Bloqueada"
    status_class = "status-success" if is_active else "status-error"
    
    if is_active:
        message = f"""
            <h2>¡Hola {user_name or 'Usuario'}!</h2>
            <div class="status-badge {status_class}">Estado de cuenta: {status_text}</div>
            <p>Nos alegra informarte que tu cuenta en <strong>MiCasita</strong> ha sido reactivada.</p>
            <p>Ya puedes volver a publicar y buscar viviendas en nuestra plataforma.</p>
            <a href="#" class="button">Ir a la App</a>
        """
    else:
        message = f"""
            <h2>Atención {user_name or 'Usuario'}</h2>
            <div class="status-badge {status_class}">Estado de cuenta: {status_text}</div>
            <p>Te informamos que tu cuenta en <strong>MiCasita</strong> ha sido suspendida temporalmente por un administrador.</p>
            <p>Durante este periodo, tus publicaciones no serán visibles para otros usuarios y no podrás realizar nuevas búsquedas.</p>
            <p>Si crees que esto es un error, por favor contacta con soporte técnico.</p>
        """
    
    return get_base_template(message)

def get_otp_template(purpose: str, code: str, name: str = None):
    greeting = f"¡Hola {name}!" if name else "¡Hola!"

    if purpose == "verify_email":
        title = "Verifica tu correo electrónico"
        body = f"""
            <h2>{greeting}</h2>
            <p>Gracias por registrarte en <strong>MiCasita</strong>. Para activar tu cuenta ingresa el siguiente código de verificación en la aplicación:</p>
            <div style="text-align:center; margin: 30px 0;">
                <span style="font-size:40px; font-weight:bold; letter-spacing:10px; color:#34216b;">{code}</span>
            </div>
            <p style="color:#6b6b80; font-size:13px;">Este código expira en <strong>24 horas</strong>. Si no creaste esta cuenta puedes ignorar este mensaje.</p>
        """
    else:
        title = "Restablecer contraseña"
        body = f"""
            <h2>{greeting}</h2>
            <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en <strong>MiCasita</strong>. Usa el siguiente código en la aplicación:</p>
            <div style="text-align:center; margin: 30px 0;">
                <span style="font-size:40px; font-weight:bold; letter-spacing:10px; color:#34216b;">{code}</span>
            </div>
            <p style="color:#6b6b80; font-size:13px;">Este código expira en <strong>15 minutos</strong>. Si no solicitaste este cambio puedes ignorar este mensaje.</p>
        """

    content = f"""
        <div style="text-align:center; margin-bottom:24px;">
            <span style="font-size:14px; font-weight:600; color:#34216b; text-transform:uppercase; letter-spacing:1px;">{title}</span>
        </div>
        {body}
    """
    return get_base_template(content)


def get_property_status_template(user_name: str, property_title: str, status: str, reason: str = None):
    status_title = "Aprobada" if status == "approved" else "Rechazada"
    status_class = "status-success" if status == "approved" else "status-error"
    
    if status == "approved":
        message = f"""
            <h2>¡Buenas noticias, {user_name or 'Usuario'}!</h2>
            <div class="status-badge {status_class}">Propiedad: {status_title}</div>
            <p>Tu propiedad <strong>"{property_title}"</strong> ha sido revisada y aprobada por nuestro equipo de moderación.</p>
            <p>¡Ya es visible para toda la comunidad de MiCasita!</p>
            <a href="#" class="button">Ver mi Publicación</a>
        """
    else:
        message = f"""
            <h2>Actualización sobre tu publicación</h2>
            <div class="status-badge {status_class}">Propiedad: {status_title}</div>
            <p>Lamentamos informarte que tu publicación <strong>"{property_title}"</strong> no ha sido aprobada en este momento.</p>
            <p><strong>Motivo:</strong> {reason or "No se especificó un motivo detallado."}</p>
            <p>Puedes editar la información de tu propiedad e intentarlo de nuevo.</p>
        """
    
    return get_base_template(message)
