# API Documentation

## Overview
The sendit Discord bot provides a comprehensive REST API for Solana wallet verification. The API is built with aiohttp and provides secure endpoints for frontend integration, health monitoring, and wallet signature validation.

## Base Configuration
- **Framework**: aiohttp web server
- **Authentication**: JWT-based token system
- **Rate Limiting**: IP-based and user-based limits
- **Port Fallback**: Automatic port selection (8080, 8081, 8082, etc.)

## Authentication System

### JWT Token Structure
```json
{
  "user_id": 123456789,
  "UUID": "550e8400-e29b-41d4-a716-446655440000",
  "iat": 1640995200,
  "exp": 1640995800
}
```

### Token Security Features
- **Short Expiration**: 10-minute token lifetime
- **Single-use**: Tokens marked as 'failed' after use
- **Custom Secret**: Environment-based JWT secret
- **Validation**: Multi-stage verification process

## API Endpoints

### POST /api/confirm
**Purpose**: Verify Solana wallet ownership through cryptographic signature

**Request Headers**:
```http
Content-Type: application/json
User-Agent: <browser-user-agent>
Origin: <frontend-origin>
```

**Request Payload**:
```json
{
  "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "wallet": "DV4ACNkpYPcE2PD3kpGGLpEKxVaKFj2TdGCyqLw8D9dV",
  "signature": "base58_encoded_signature"
}
```

**Success Response** (200):
```json
{
  "status": "success",
  "message": "Wallet verified successfully!",
  "timestamp": 1640995200
}
```

**Error Responses**:
- **400 Bad Request**: Invalid request data, missing fields, or malformed input
- **401 Unauthorized**: Invalid or expired JWT token
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server or database error

### GET /api/health
**Purpose**: Service health check for monitoring and load balancers

**Request**:
```http
GET /api/health
```

**Success Response** (200):
```json
{
  "status": "healthy",
  "service": "solana_verification",
  "timestamp": 1640995200
}
```

**Error Response** (503):
```json
{
  "status": "unhealthy",
  "error": "Database connection failed"
}
```

## Validation Process

### JWT Validation
1. **Signature Verification**: Validates JWT signature with custom secret
2. **Expiration Check**: Ensures token hasn't expired
3. **Structure Validation**: Verifies required fields (user_id, UUID)
4. **Database Lookup**: Confirms token exists and is pending

### Wallet Address Validation
```python
def validate_solana_address(self, address: str) -> bool:
    try:
        decoded = b58decode(address)
        return len(decoded) == 32  # Solana public keys are 32 bytes
    except Exception:
        return False
```

### Signature Verification
```python
# Expected message format
expected_message = f"Confirming wallet ownership for request: {token_uuid}"

# Cryptographic verification
verify_key = nacl.signing.VerifyKey(public_key_bytes)
verify_key.verify(message_bytes, signature_bytes)
```

## Rate Limiting

### Configuration
- **Window**: 60 seconds
- **Limit**: 10 requests per IP per minute
- **Cleanup**: Automatic old entry removal
- **Headers**: Rate limit information in response headers

### Implementation
```python
async def rate_limit_middleware(self, request, handler):
    client_ip = request.remote
    if 'X-Forwarded-For' in request.headers:
        client_ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
    
    # Rate limit checking and enforcement
    if len(self.rate_limiter[client_ip]) >= self.rate_limit_max_requests:
        return web.json_response(
            {'status': 'error', 'message': 'Rate limit exceeded'},
            status=429
        )
```

## Error Handling

### Error Response Format
```json
{
  "status": "error",
  "message": "Human-readable error message",
  "timestamp": 1640995200
}
```

### Error Categories

#### Authentication Errors
- **Invalid JWT**: Malformed or tampered token
- **Expired Token**: Token past expiration time
- **Token Not Found**: Token not in database
- **User ID Mismatch**: JWT user doesn't match database

#### Validation Errors
- **Missing Data**: Required fields not provided
- **Invalid Wallet**: Base58 decoding failure
- **Invalid Signature**: Cryptographic verification failure
- **Signature Length**: Signature format validation

#### Security Errors
- **Rate Limited**: Too many requests from IP
- **Token Not Pending**: Token already used or expired
- **Status Invalid**: Token not in correct state

#### System Errors
- **Database Error**: Database connectivity issues
- **Internal Error**: Unexpected server errors

## Security Features

### Request Validation
- **Input Sanitization**: All inputs validated and sanitized
- **Length Checks**: Signature and address length validation
- **Format Validation**: Base58 encoding verification
- **Origin Validation**: CORS and origin checking

### Database Security
- **SQL Escaping**: Custom escaping for Transaction pooler
- **Connection Pooling**: Secure connection management
- **Error Masking**: Generic error messages to users
- **Audit Logging**: Complete request logging

### Token Security
- **Cryptographic Verification**: Strong signature validation
- **Replay Prevention**: Single-use token enforcement
- **Expiration Enforcement**: Strict time-based validation
- **Status Tracking**: Complete token lifecycle monitoring

## Integration Examples

### JavaScript Frontend Integration
```javascript
class SolanaVerificationClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async verifyWallet(jwt, walletAddress, signature) {
    const response = await fetch(`${this.baseUrl}/api/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jwt,
        wallet: walletAddress,
        signature
      })
    });

    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.message || 'Verification failed');
    }
    
    return data;
  }
}
```

### React Hook Example
```jsx
import { useState, useCallback } from 'react';

export const useWalletVerification = (apiClient) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const verifyWallet = useCallback(async (jwt, walletAddress, signature) => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await apiClient.verifyWallet(jwt, walletAddress, signature);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [apiClient]);

  return { verifyWallet, loading, error };
};
```

## Message Format Requirements

### Exact Message Format
The frontend must ensure users sign this exact message:
```
Confirming wallet ownership for request: {UUID}
```

### Critical Requirements
- **Exact Text**: No variations in spelling or punctuation
- **UUID Substitution**: Replace {UUID} with actual token UUID
- **UTF-8 Encoding**: Message must be UTF-8 encoded for verification
- **No Extra Characters**: No additional whitespace or characters

## Monitoring and Logging

### Request Logging
All API requests are logged with:
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "method": "POST",
  "endpoint": "/api/confirm",
  "user_id": 123456789,
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "response_code": 200,
  "duration_ms": 1250
}
```

### Health Monitoring
- **Database Connectivity**: Health endpoint tests database
- **Response Times**: Average and percentile tracking
- **Error Rates**: Success/failure ratio monitoring
- **Rate Limit Metrics**: Request volume and blocking stats

### Performance Metrics
- **Verification Success Rate**: >95% target
- **Average Response Time**: <500ms target
- **Database Query Time**: <100ms target
- **Token Cleanup Efficiency**: Expired token removal rate

## Deployment Configuration

### Direct Server Deployment (No Nginx Required)

The bot runs its own HTTP/HTTPS server directly without requiring Nginx reverse proxy:

### Environment Variables
```env
DISCORD_TOKEN=your_discord_bot_token
DATABASE_URL=postgresql://user:pass@host:port/dbname
JWT_SECRET=your_very_secure_random_string_minimum_32_characters_long

# Optional SSL Configuration (for HTTPS)
SSL_CERT_PATH=/etc/letsencrypt/live/custom_domain.app/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/custom_domain.app/privkey.pem
PORT=8080
```

### config.json Settings
```json
{
  "server": {
    "port": 8080,
    "host": "0.0.0.0",
    "ssl": {
      "enabled": false,
      "cert_path": "/etc/letsencrypt/live/custom_domain.app/fullchain.pem",
      "key_path": "/etc/letsencrypt/live/custom_domain.app/privkey.pem"
    },
    "cors": {
      "origins": ["https://discord-verif-webapp.vercel.app", "http://localhost:3000"],
      "methods": ["GET", "POST", "OPTIONS"],
      "headers": ["Content-Type", "Authorization"]
    }
  },
  "features": {
    "solana_verification": {
      "vercel_frontend_url": "https://discord-verif-webapp.vercel.app"
    }
  }
}
```

### SSL Certificate Setup (Optional)
For HTTPS support, use Let's Encrypt:
```bash
# Install certbot
sudo apt install certbot

# Generate certificates
sudo certbot certonly --standalone -d custom_domain.app

# Set environment variables
export SSL_CERT_PATH="/etc/letsencrypt/live/custom_domain.app/fullchain.pem"
export SSL_KEY_PATH="/etc/letsencrypt/live/custom_domain.app/privkey.pem"
```

### Firewall Configuration
```bash
# Allow HTTP (port 80) and HTTPS (port 443)
sudo ufw allow 80
sudo ufw allow 443

# Or allow custom port
sudo ufw allow 8080
```

## Testing

### Health Check Test
```bash
curl -X GET http://localhost:8080/api/health
```

### Verification Test
```bash
curl -X POST http://localhost:8080/api/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "jwt": "test_jwt_token",
    "wallet": "DV4ACNkpYPcE2PD3kpGGLpEKxVaKFj2TdGCyqLw8D9dV",
    "signature": "test_signature"
  }'
```

## Maintenance Notes

### Regular Tasks
- **JWT Secret Rotation**: Periodic secret updates
- **Rate Limit Monitoring**: Adjust limits based on usage
- **Database Cleanup**: Token cleanup task monitoring
- **Log Analysis**: Regular error pattern analysis

### Performance Optimization
- **Connection Pooling**: Efficient database usage
- **Memory Management**: Rate limiter cleanup
- **Response Caching**: Consider caching for repeated requests
- **Database Indexing**: Optimize token lookup queries

### Security Updates
- **Dependency Updates**: Regular security patches
- **Token Validation**: Enhanced validation logic
- **Error Handling**: Improved error message security
- **Audit Logging**: Enhanced logging for security events