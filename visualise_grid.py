from flask import Flask, render_template_string
import requests

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title></title>
    <style>
        body { background: #000; color: #fff; }
        .grid { display: flex; }
        .column { margin: 10px; }
        .column h2 { text-align: center; color: #fff; }
        .img-box { margin: 5px; text-align: center; }
        img { max-width: 150px; max-height: 150px; border: 1px solid #ccc; }
    </style>
    <script>
        let lastAssignments = null;
        function fetchAndUpdate() {
            fetch('/assignments_json')
                .then(response => response.json())
                .then(data => {
                    const assignments = data.assignments;
                    if (JSON.stringify(assignments) !== JSON.stringify(lastAssignments)) {
                        lastAssignments = assignments;
                        updateGrid(assignments);
                    }
                });
        }
        function updateGrid(assignments) {
            const grid = document.getElementById('grid');
            grid.innerHTML = '';
            Object.entries(assignments).forEach(([pi, images]) => {
                const col = document.createElement('div');
                col.className = 'column';
                const h2 = document.createElement('h2');
                h2.textContent = 'Pi ' + pi;
                col.appendChild(h2);
                images.forEach(img => {
                    const box = document.createElement('div');
                    box.className = 'img-box';
                    const image = document.createElement('img');
                    image.src = '/exhibition/' + img;
                    image.alt = '';
                    box.appendChild(image);
                    // Hide filename label
                    // const label = document.createElement('div');
                    // label.textContent = img;
                    // box.appendChild(label);
                    col.appendChild(box);
                });
                grid.appendChild(col);
            });
        }
        document.addEventListener('DOMContentLoaded', function() {
            fetchAndUpdate();
            setInterval(fetchAndUpdate, 5000);
        });
    </script>
</head>
<body>
    <div class="grid" id="grid">
        <!-- Grid will be populated by JS -->
    </div>
</body>
</html>
"""

@app.route("/")
def grid():
    # Initial render, assignments will be loaded by JS
    return render_template_string(TEMPLATE)

# New endpoint for AJAX fetch
@app.route("/assignments_json")
def assignments_json():
    resp = requests.get("http://localhost:5001/images/all")
    data = resp.json()
    assignments = {str(k): v for k, v in data["assignments"].items()}
    return {"assignments": assignments}

# Serve images from the exhibition folder
from flask import send_from_directory
import os

@app.route("/exhibition/<path:filename>")
def exhibition_image(filename):
    exhibition_dir = os.path.join(os.path.dirname(__file__), "exhibition")
    return send_from_directory(exhibition_dir, filename)

if __name__ == "__main__":
    app.run(port=5002, debug=True)
