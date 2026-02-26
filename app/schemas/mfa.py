from pydantic import BaseModel, Field


class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_data_uri: str | None = None  # data: URI for inline QR display; None if qrcode not installed


class MFAConfirmRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFADisableRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFAStatusResponse(BaseModel):
    mfa_enabled: bool
