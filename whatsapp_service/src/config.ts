import dotenv from 'dotenv';
dotenv.config();

export const config = {
  PORT: process.env.PORT || 3001,
  DJANGO_BACKEND_URL: process.env.DJANGO_BACKEND_URL || 'http://127.0.0.1:8000',
  INTERNAL_API_SECRET: process.env.INTERNAL_API_SECRET || 'scaleezy_internal_secret_key_2026',
  NODE_ENV: process.env.NODE_ENV || 'development'
};
