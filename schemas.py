from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    csrf_token: str
class UserRead(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True  

class UserLogin(BaseModel):
    username: str
    password: str
