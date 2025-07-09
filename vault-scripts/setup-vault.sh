#!/bin/sh

# Ce script attend que Vault soit prêt, puis y injecte les secrets.

# set -e : Arrête le script si une commande échoue
set -e

# 1. Attendre que Vault soit accessible et descellé
# On utilise le `healthcheck` de Docker Compose, mais une boucle est une sécurité supplémentaire.
echo "Attente de la disponibilité de Vault..."
until vault status -address="$VAULT_ADDR" > /dev/null 2>&1; do
  echo "Vault n'est pas encore prêt, nouvelle tentative dans 2 secondes..."
  sleep 2
done
echo "Vault est prêt !"

# 2. S'authentifier avec le token racine
echo "Authentification avec le token racine..."
vault login -address="$VAULT_ADDR" "$VAULT_TOKEN"

# 3. Activer le moteur de secrets KV v2 au chemin 'secret' (nécessaire sur un serveur dev frais)
# L'option -update permet de ne pas échouer si le moteur existe déjà
vault secrets enable -address="$VAULT_ADDR" -path=secret -update kv-v2 || echo "Moteur KV 'secret' déjà activé."
echo "Moteur KV 'secret' activé."

# 4. Écrire le secret de la base de données en utilisant les variables d'environnement
echo "Écriture du secret de la base de données dans Vault..."
vault kv put -address="$VAULT_ADDR" secret/testvault \
    db_user="$DB_USER_FOR_APP" \
    db_password="$DB_PASSWORD_FOR_APP"

echo "Configuration de Vault terminée avec succès !"