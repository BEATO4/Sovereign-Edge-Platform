use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct AsapClaims {
    pub iss: String,
    pub sub: Option<String>,
    pub aud: Vec<String>,
    pub exp: usize,
    pub nbf: Option<usize>,
    pub iat: usize,
    pub jti: String,
    #[serde(default)]
    pub tenant_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ValidationResult {
    pub is_valid: bool,
    pub caller: Option<String>,
    pub tenant_id: Option<String>,
    pub error_reason: Option<String>,
}
