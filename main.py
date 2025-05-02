import os
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import boto3

# load .env
load_dotenv()

AWS_REGION   = os.getenv("AWS_REGION", "us-east-1")
BUCKET_NAME  = os.getenv("BUCKET_NAME")
# boto3 will pick up AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY from env or ~/.aws/credentials
s3 = boto3.client("s3", region_name=AWS_REGION)

class URLResponse(BaseModel):
    url: str
    key: str

app = FastAPI()

@app.post("/api/upload-url", response_model=URLResponse)
def generate_presigned_url():
    # unique object key
    key = f"uploads/{uuid.uuid4()}.pdf"
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": key,
            "ContentType": "application/pdf"
        },
        ExpiresIn=900,       # URL valid for 15 minutes
        HttpMethod="PUT"     # ensure PUT is allowed
    )
    return URLResponse(url=url, key=key)
