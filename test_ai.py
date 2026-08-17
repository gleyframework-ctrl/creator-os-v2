import requests
q = "What is the W.E.B. analysis and how do I use it to find the secret desire of a 40-year-old executive?"
r = requests.post('http://localhost:8000/api/chat', json={'question': q})
print(r.text)
