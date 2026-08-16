import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is online!", 200

@app.route('/health')
def health():
    return "Healthy", 200

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=PORT)
