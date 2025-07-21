# Solana Verify Cog Documentation

## Overview
The Solana Verify cog (`cogs/solana_verify.py`) provides secure Solana wallet verification through JWT-based authentication and cryptographic signature validation. It runs an integrated API server for frontend interaction and handles the complete verification workflow.

## Core Components

### VerificationView Class
A persistent Discord UI View for wallet verification button interactions.

**Key Features:**
- `timeout=None` for persistence across bot restarts
- Custom ID: `solana_verify_button` for reliable tracking
- Spam prevention with pending token reuse
- Ephemeral responses for privacy

### SolanaVerify Cog Class
Main cog that manages wallet verification, API server, and token cleanup.

**Key Features:**
- Integrated aiohttp web server
- JWT token generation and validation
- Rate limiting middleware
- Automatic token cleanup
- Cryptographic signature verification

## User Flow

1. **User Interaction**: User clicks "Confirm Wallet" button
2. **Token Generation**: Bot creates unique UUID and JWT token
3. **Link Provision**: User receives ephemeral verification link
4. **Frontend Verification**: User connects wallet and signs message
5. **API Validation**: Backend validates JWT, signature, and token
6. **Role Assignment**: Bot grants verified role and sends confirmation

## Technical Implementation

### JWT Token Structure
```json
{
  "user_id": 123456789,
  "UUID": "550e8400-e29b-41d4-a716-446655440000",
  "exp": 1640995800
}
```

### Database Integration
- **User Creation**: `create_or_get_user()` ensures user exists
- **Token Storage**: `insert_verification_token()` stores pending verifications
- **Status Updates**: `update_verification_status()` tracks token lifecycle
- **User Verification**: `update_user_solana_verified()` marks user as verified

### Security Features

#### Rate Limiting
- **IP-based**: 10 requests per minute per IP address
- **User-based**: Prevents multiple pending tokens
- **Middleware**: aiohttp middleware for API endpoints

#### Token Security
- **Expiration**: 10-minute token lifetime
- **Single-use**: Tokens marked as 'failed' after use
- **Validation**: JWT signature verification with custom secret
- **Cleanup**: Automatic removal of expired tokens every 30 minutes

#### Signature Validation
```python
# Message format validation
expected_message = f"Confirming wallet ownership for request: {token_uuid}"

# Cryptographic verification using nacl
verify_key = nacl.signing.VerifyKey(public_key_bytes)
verify_key.verify(message_bytes, signature_bytes)
```

### API Endpoints

The API server runs internally on the port specified by `api_port`. When deployed behind the centralized Nginx reverse proxy, these endpoints are accessible under the `/api/` path.

#### `POST /api/confirm`
**Purpose**: Handle wallet verification from the frontend.
**Payload**:
```json
{
  "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "wallet": "DV4ACNkpYPcE2PD3kpGGLpEKxVaKFj2TdGCyqLw8D9dV",
  "signature": "base58_encoded_signature"
}
```

#### `GET /api/health`
**Purpose**: Health check for monitoring services.
**Response**:
```json
{
  "status": "healthy",
  "service": "solana_verification",
  "timestamp": 1640995200
}
```

## Configuration Requirements

### config.json Settings
```json
{
  "api_port": 8080, // Internal port for the API server. Not exposed when using Nginx.
  "vercel_frontend_url": "https://your-frontend.vercel.app",
  "verification_channel_id": 123456789012345680,
  "verified_role_id": 123456789012345680,
  "guild_id": 123456789012345678,
  "solana_rpc_url": "https://api.mainnet-beta.solana.com"
}
```

### Environment Variables
```env
JWT_SECRET=your_very_secure_random_string_minimum_32_characters_long
```

### messages.json Integration
Uses centralized messages from `messages.json`:
- `solana_wallet_verification.verification_persistent_title`: Button embed title
- `solana_wallet_verification.already_verified`: Already verified message
- `solana_wallet_verification.verification_pending`: Pending verification message
- `solana_wallet_verification.verification_link_ephemeral`: Verification link message
- `solana_wallet_verification.verification_success_dm`: Success DM
- `solana_wallet_verification.verification_success_frontend`: Frontend success message

## Commands

### `/verify-wallet` (Hybrid Command)
- **Access**: Team members only (role ID: 1393391086877282320)
- **Purpose**: Post persistent verification message in verification channel
- **Usage**: Creates embed with VerificationView button
- **Response**: Ephemeral confirmation of message posting

## Background Tasks

### Token Cleanup Task
- **Frequency**: Every 30 minutes
- **Operations**:
  - Mark expired tokens as 'expired'
  - Delete tokens older than 7 days
  - Log cleanup statistics

## Error Handling

### Validation Errors
- **Invalid JWT**: Token signature verification failure
- **Expired Token**: Token past expiration time
- **Missing Data**: Incomplete verification request
- **Invalid Wallet**: Base58 decoding failure
- **Signature Mismatch**: Cryptographic verification failure

### Database Errors
- **Connection Issues**: Handled by `handle_db_error()` utility
- **User-friendly Messages**: Generic error responses to users
- **Detailed Logging**: Full error context for debugging

### Permission Errors
- **Role Assignment**: Graceful handling of missing permissions
- **Channel Access**: Validation of channel configuration
- **DM Delivery**: Fallback handling for blocked DMs

## Bot Permissions Required

- **Send Messages**: For verification embeds and responses
- **Embed Links**: For rich verification embeds
- **Manage Roles**: For verified role assignment
- **View Channel**: For accessing verification channel
- **Use Application Commands**: For button interactions

## Security Considerations

### Data Protection
- **Ephemeral Responses**: Private verification links
- **No Data Exposure**: Generic error messages
- **Secure Token Storage**: Database-backed token management

### Attack Prevention
- **Rate Limiting**: Prevents spam attacks
- **Token Validation**: Prevents replay attacks
- **Signature Verification**: Prevents impersonation
- **CORS Protection**: Origin validation for API requests

### Audit Trail
- **Comprehensive Logging**: All verification attempts logged
- **Status Tracking**: Complete token lifecycle tracking
- **Error Context**: Detailed error information for investigation

### Dependencies
Lightweight alternatives to heavy packages:
- `httpx` instead of full Solana SDK
- `base58` for address validation
- `pynacl` for signature verification

## Integration Points

### Frontend Integration
- **Vercel Deployment**: Configured via `vercel_frontend_url`
- **JWT Handoff**: Secure token transmission
- **Message Signing**: Exact message format requirement

### Database Layer
- **Transaction Pooler**: Compatible with Supabase pooling
- **Escaped SQL**: Custom escaping for security
- **Connection Pooling**: Efficient resource usage

### Discord Integration
- **Role Management**: Automatic verified role assignment
- **DM Notifications**: Success confirmation messages
- **Channel Management**: Persistent verification interface

## Monitoring and Metrics

### Health Monitoring
- **Database Connectivity**: Health check endpoint validation
- **API Availability**: Service status monitoring
- **Token Cleanup**: Automatic maintenance logging

### Success Metrics
- **Verification Rate**: >80% successful completion target
- **Response Time**: <2 second API response time
- **Error Rate**: <5% verification failure rate

### Logging Patterns
```
INFO: Generated new verification token {token_uuid} for user {user_id}
INFO: User {user_id} ({wallet_address}) successfully verified
WARNING: Rate limit exceeded for IP {client_ip}
ERROR: Invalid or expired JWT received: {error}
```

## Maintenance Notes

### Token Lifecycle
- **Generation**: UUID v4 with 10-minute expiration
- **Validation**: Multi-stage verification process
- **Cleanup**: Automatic expired token removal

### Security Updates
- **JWT Secret Rotation**: Regular secret updates recommended
- **Dependency Updates**: Monitor nacl and base58 for security patches
- **Rate Limit Tuning**: Adjust limits based on usage patterns