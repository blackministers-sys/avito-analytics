from flask import Flask, request

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <h1>Avito Analytics</h1>
    <p>Система аналитики запущена.</p>
    <p>Следующий этап — подключение Avito API.</p>
    """


@app.route("/callback")
def callback():
    code = request.args.get("code")

    if code:
        return f"""
        <h1>Avito API</h1>
        <p>Код авторизации получен.</p>
        <p>Можно продолжать подключение.</p>
        """

    error = request.args.get("error")

    if error:
        return f"""
        <h1>Ошибка авторизации</h1>
        <p>{error}</p>
        """

    return """
    <h1>Avito Analytics</h1>
    <p>Callback работает, но код авторизации пока не передан.</p>
    """


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
