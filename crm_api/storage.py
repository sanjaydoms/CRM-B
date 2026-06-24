from django.core.files.storage import Storage
from django.conf import settings
import requests
import mimetypes
from io import BytesIO

class SupabaseStorage(Storage):
    def __init__(self, bucket_name=None, supabase_url=None, supabase_key=None):
        self.bucket_name = bucket_name or getattr(settings, 'SUPABASE_BUCKET', 'boutique-crm')
        self.supabase_url = supabase_url or getattr(settings, 'SUPABASE_URL', '')
        self.supabase_key = supabase_key or getattr(settings, 'SUPABASE_KEY', '')

    def _open(self, name, mode='rb'):
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{name}"
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "ApiKey": self.supabase_key,
        }
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return BytesIO(res.content)
        raise FileNotFoundError(f"File {name} not found on Supabase Storage")

    def _save(self, name, content):
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{name}"
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "ApiKey": self.supabase_key,
        }
        
        # Read the file content
        content_bytes = content.read()
        mime_type, _ = mimetypes.guess_type(name)
        if mime_type:
            headers["Content-Type"] = mime_type
            
        res = requests.post(url, headers=headers, data=content_bytes)
        
        # If file already exists, retry with x-upsert header to overwrite it
        if res.status_code != 200:
            headers["x-upsert"] = "true"
            res = requests.post(url, headers=headers, data=content_bytes)
            
        if res.status_code != 200:
            raise Exception(f"Failed to upload to Supabase: {res.text}")
            
        return name

    def exists(self, name):
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{name}"
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "ApiKey": self.supabase_key,
        }
        res = requests.head(url, headers=headers)
        return res.status_code == 200

    def url(self, name):
        return f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{name}"

    def delete(self, name):
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{name}"
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "ApiKey": self.supabase_key,
        }
        res = requests.delete(url, headers=headers)
        return res.status_code == 200
