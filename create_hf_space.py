from huggingface_hub import HfApi
api = HfApi()
token = 'YOUR_HF_TOKEN'
api.create_repo(
    repo_id='neohacker51/neo-downloader',
    repo_type='space',
    space_sdk='docker',
    private=False,
    exist_ok=True,
    token=token,
)
print("Space created!")
print("URL: https://huggingface.co/spaces/neohacker51/neo-downloader")
