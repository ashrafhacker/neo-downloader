from huggingface_hub import HfApi
api = HfApi()
user = api.whoami(token='YOUR_HF_TOKEN')
print(f"User: {user['name']}")
print(f"Full: {user}")
