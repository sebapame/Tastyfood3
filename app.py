from flask import Flask, render_template, request, redirect, url_for, send_file
from datetime import datetime
from pytz import timezone
import pandas as pd
from io import BytesIO
from sqlalchemy import create_engine, text
import os

app = Flask(__name__)
tz = timezone("America/Santiago")

# Conexión a PostgreSQL desde Render
db_url = os.environ.get("DATABASE_URL") or "postgresql://usuario:clave@localhost:5432/estacionamiento"
engine = create_engine(db_url)

def get_time_now():
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = ""
    filtro_fecha = request.args.get("fecha", datetime.now(tz).strftime("%Y-%m-%d"))
    mostrar_monto = False
    minutos = 0
    monto = 0
    ultima_salida_id = None

    with engine.connect() as conn:
        if request.method == "POST":
            patente = request.form["patente"].upper()
            now = get_time_now()
            medio_pago = request.form.get("medio_pago", "")

            result = conn.execute(text("SELECT * FROM registros WHERE patente = :patente AND hora_salida IS NULL"),
                                  {"patente": patente}).fetchone()

            if result:
                # Salida
                hora_entrada = datetime.strptime(result["hora_entrada"], "%Y-%m-%d %H:%M:%S")
                hora_salida = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
                minutos = int((hora_salida - hora_entrada).total_seconds() / 60)
                monto_bruto = 500 if minutos <= 15 else 500 + (minutos - 15) * 24
                unidad = monto_bruto % 10
                if unidad < 5:
                    monto = monto_bruto - unidad
                else:
                    monto = monto_bruto + (10 - unidad)

                if medio_pago:
                    conn.execute(text("""
                        UPDATE registros SET hora_salida = :salida, monto = :monto, medio_pago = :medio
                        WHERE id = :id
                    """), {
                        "salida": now,
                        "monto": monto,
                        "medio": medio_pago,
                        "id": result["id"]
                    })
                    return redirect(url_for('index', fecha=filtro_fecha))
                else:
                    mostrar_monto = True
            else:
                # Ingreso
                conn.execute(text("INSERT INTO registros (patente, hora_entrada) VALUES (:patente, :entrada)"),
                             {"patente": patente, "entrada": now})
                return redirect(url_for('index', fecha=filtro_fecha))

        # Obtener registros ordenados
        registros_restantes = conn.execute(text("""
            SELECT * FROM registros
            WHERE DATE(hora_entrada) = :fecha AND hora_salida IS NULL
            ORDER BY hora_entrada ASC
        """), {"fecha": filtro_fecha}).fetchall()

        ultima_salida = conn.execute(text("""
            SELECT * FROM registros
            WHERE DATE(hora_entrada) = :fecha AND hora_salida IS NOT NULL
            ORDER BY hora_salida DESC
            LIMIT 1
        """), {"fecha": filtro_fecha}).fetchone()

        registros_anteriores = conn.execute(text("""
            SELECT * FROM registros
            WHERE DATE(hora_entrada) = :fecha AND hora_salida IS NOT NULL
            AND id != :ultima_id
            ORDER BY hora_salida DESC
        """), {
            "fecha": filtro_fecha,
            "ultima_id": ultima_salida["id"] if ultima_salida else -1
        }).fetchall()

        registros = registros_restantes
        if ultima_salida:
            registros += [ultima_salida]
            ultima_salida_id = ultima_salida["id"]
        registros += registros_anteriores

        # Totales por medio de pago
        totales_query = conn.execute(text("""
            SELECT medio_pago, SUM(monto) FROM registros
            WHERE DATE(hora_entrada) = :fecha AND monto IS NOT NULL
            GROUP BY medio_pago
        """), {"fecha": filtro_fecha})
        totales = {("Prepago" if k == "Transferencia" else k): v for k, v in totales_query.fetchall()}
        total_general = sum(totales.values()) if totales else 0

    return render_template("index.html", registros=registros, mensaje=mensaje, fecha=filtro_fecha,
                           mostrar_monto=mostrar_monto, minutos=minutos, monto=monto,
                           totales=totales, total_general=total_general,
                           ultima_salida_id=ultima_salida_id)

@app.route("/exportar")
def exportar():
    fecha = request.args.get("fecha")
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT * FROM registros WHERE DATE(hora_entrada) = :fecha"),
                         conn, params={"fecha": fecha})
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name=f"registros_{fecha}.xlsx", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)

