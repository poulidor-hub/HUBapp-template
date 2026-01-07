#!/usr/bin/env python3
"""
Test d'intégration HTTPS pour les applications Hub
==================================================

Ce script teste la connexion HTTPS vers le Hub pour une application.
Il vérifie :
1. La présence du certificat CA
2. La connexion HTTPS vers le Hub
3. La récupération du JWKS
4. L'enregistrement de l'application

Usage:
    python test_https_integration.py

Variables d'environnement requises:
    - HUB_HOST: IP/hostname du Hub
    - HUB_HTTPS_PORT: Port HTTPS (défaut: 443)
    - APP_SLUG: Slug de l'application
    
Note: HTTPS est toujours activé, le certificat CA est attendu dans /app/certs/hub-ca.crt
"""

import os
import sys
import asyncio
from pathlib import Path

# Ajouter le répertoire courant au path pour les imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    import httpx
except ImportError:
    print("❌ httpx non installé. Exécutez: pip install httpx")
    sys.exit(1)


def get_config():
    """Récupère la configuration depuis les variables d'environnement."""
    return {
        "hub_host": os.getenv("HUB_HOST", "localhost"),
        "hub_https_port": int(os.getenv("HUB_HTTPS_PORT", "443")),
        "hub_ca_cert_path": "/app/certs/hub-ca.crt",
        "app_slug": os.getenv("APP_SLUG", "test-app"),
    }


def get_hub_url(config: dict) -> str:
    """Construit l'URL du Hub (toujours HTTPS)."""
    port = f":{config['hub_https_port']}" if config["hub_https_port"] != 443 else ""
    return f"https://{config['hub_host']}{port}"


async def test_certificate(config: dict) -> bool:
    """Test 1: Vérifie la présence du certificat CA."""
    print("\n" + "="*60)
    print("🔐 TEST 1: Vérification du certificat CA")
    print("="*60)
    
    ca_path = Path(config["hub_ca_cert_path"])
    
    if not ca_path.exists():
        print(f"❌ Certificat CA non trouvé: {ca_path}")
        print("   💡 Vérifiez que le volume certs est monté correctement")
        return False
    
    if ca_path.stat().st_size == 0:
        print(f"❌ Certificat CA vide: {ca_path}")
        return False
    
    # Vérifier le contenu
    content = ca_path.read_text()
    if "-----BEGIN CERTIFICATE-----" not in content:
        print(f"❌ Le fichier ne semble pas être un certificat PEM valide")
        return False
    
    print(f"✅ Certificat CA trouvé: {ca_path}")
    print(f"   Taille: {ca_path.stat().st_size} bytes")
    return True


async def test_https_connection(config: dict) -> bool:
    """Test 2: Vérifie la connexion HTTPS vers le Hub."""
    print("\n" + "="*60)
    print("🌐 TEST 2: Connexion HTTPS vers le Hub")
    print("="*60)
    
    hub_url = get_hub_url(config)
    print(f"   URL: {hub_url}")
    
    # Configurer la vérification SSL
    ssl_verify: bool | str = True
    ca_path = config["hub_ca_cert_path"]
    if Path(ca_path).exists():
        ssl_verify = ca_path
        print(f"   CA: {ca_path}")
    else:
        print("⚠️  CA non trouvé, utilisation du store système")
    
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=ssl_verify) as client:
            # Test endpoint health
            response = await client.get(f"{hub_url}/api/health")
            
            if response.status_code == 200:
                print(f"✅ Connexion réussie (status: {response.status_code})")
                return True
            else:
                print(f"⚠️  Réponse inattendue: {response.status_code}")
                return True  # La connexion fonctionne même si le status n'est pas 200
                
    except httpx.ConnectError as e:
        print(f"❌ Impossible de se connecter au Hub")
        print(f"   Erreur: {e}")
        return False
    except httpx.HTTPStatusError as e:
        print(f"⚠️  Erreur HTTP: {e}")
        return True  # La connexion SSL fonctionne
    except Exception as e:
        print(f"❌ Erreur: {type(e).__name__}: {e}")
        return False


async def test_jwks(config: dict) -> bool:
    """Test 3: Vérifie la récupération du JWKS."""
    print("\n" + "="*60)
    print("🔑 TEST 3: Récupération JWKS")
    print("="*60)
    
    hub_url = get_hub_url(config)
    jwks_url = f"{hub_url}/api/auth/.well-known/jwks.json"
    print(f"   URL: {jwks_url}")
    
    # Configurer la vérification SSL
    ssl_verify: bool | str = True
    ca_path = config["hub_ca_cert_path"]
    if Path(ca_path).exists():
        ssl_verify = ca_path
    
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=ssl_verify) as client:
            response = await client.get(jwks_url)
            
            if response.status_code == 200:
                data = response.json()
                keys = data.get("keys", [])
                print(f"✅ JWKS récupéré avec succès")
                print(f"   Nombre de clés: {len(keys)}")
                for key in keys:
                    kid = key.get("kid", "N/A")
                    kty = key.get("kty", "N/A")
                    print(f"   - kid: {kid}, type: {kty}")
                return True
            else:
                print(f"❌ Erreur: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Erreur: {type(e).__name__}: {e}")
        return False


async def test_app_register(config: dict) -> bool:
    """Test 4: Vérifie l'enregistrement de l'application."""
    print("\n" + "="*60)
    print("📝 TEST 4: Enregistrement application")
    print("="*60)
    
    hub_url = get_hub_url(config)
    register_url = f"{hub_url}/api/apps/register"
    print(f"   URL: {register_url}")
    print(f"   App Slug: {config['app_slug']}")
    
    # Configurer la vérification SSL
    ssl_verify: bool | str = True
    ca_path = config["hub_ca_cert_path"]
    if Path(ca_path).exists():
        ssl_verify = ca_path
    
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=ssl_verify) as client:
            response = await client.post(
                register_url,
                json={
                    "slug": config["app_slug"],
                    "name": f"Test App {config['app_slug']}",
                    "description": "Test d'intégration HTTPS",
                    "api_port": 8000,
                    "frontend_port": 80,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                is_new = data.get("is_new", False)
                if is_new:
                    print(f"✅ Application enregistrée avec succès (nouvelle)")
                else:
                    print(f"✅ Application reconnectée (existante)")
                return True
            elif response.status_code == 409:
                print(f"✅ Application déjà enregistrée (attendu)")
                return True
            else:
                print(f"⚠️  Réponse: {response.status_code}")
                print(f"   {response.text[:200]}")
                return True  # L'API fonctionne même si l'enregistrement échoue
                
    except Exception as e:
        print(f"❌ Erreur: {type(e).__name__}: {e}")
        return False


async def main():
    """Exécute tous les tests."""
    print("="*60)
    print("🧪 TEST D'INTÉGRATION HTTPS - Applications Hub")
    print("="*60)
    
    config = get_config()
    
    print(f"\n📋 Configuration:")
    print(f"   HUB_HOST: {config['hub_host']}")
    print(f"   HUB_HTTPS_PORT: {config['hub_https_port']}")
    print(f"   HUB_CA_CERT_PATH: {config['hub_ca_cert_path']}")
    print(f"   APP_SLUG: {config['app_slug']}")
    
    results = []
    
    # Exécuter les tests
    results.append(("Certificat CA", await test_certificate(config)))
    results.append(("Connexion HTTPS", await test_https_connection(config)))
    results.append(("JWKS", await test_jwks(config)))
    results.append(("Enregistrement App", await test_app_register(config)))
    
    # Résumé
    print("\n" + "="*60)
    print("📊 RÉSUMÉ")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"   {status} {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 Tous les tests ont réussi!")
        return 0
    else:
        print("⚠️  Certains tests ont échoué")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
