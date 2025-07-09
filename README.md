# Projet TestVault : Sécurisation d'une Application Web

Ce projet est une application web de démonstration conçue pour illustrer un ensemble complet de bonnes pratiques de sécurité modernes. Elle part d'une application simple (afficher une liste de livres) et y ajoute progressivement des couches de sécurité robustes : gestion centralisée des secrets, authentification forte, et protections contre les attaques courantes.

L'ensemble de l'environnement est conteneurisé avec **Docker** et orchestré par **Docker Compose**, garantissant un lancement simple et reproductible sur n'importe quelle machine.

## Fonctionnalités Clés

*   **Gestion Centralisée des Secrets** : Les identifiants de la base de données ne sont pas stockés dans le code ou les fichiers de configuration, mais sont récupérés dynamiquement depuis un coffre-fort **HashiCorp Vault**.
*   **Authentification Multi-Facteurs (MFA/2FA)** : Prise en charge de la double authentification via **TOTP** (Time-based One-Time Password), compatible avec des applications comme Google Authenticator ou Authy.
*   **Protection contre les Attaques par Rejeu** : Implémentation d'un mécanisme de nonce et de timestamp pour empêcher qu'une requête (création de compte, connexion...) puisse être interceptée et réutilisée par un attaquant.
*   **Protection contre les Bots** : Un **Captcha** côté serveur est intégré au formulaire de connexion pour décourager les tentatives d'automatisation et de brute-force.
*   **Stratégie de Gouvernance des Comptes** : Le système est conçu pour permettre la détection et la gestion des comptes obsolètes ou inactifs.
*   **Environnement Conteneurisé** : L'application (Flask), la base de données (MariaDB) et le coffre-fort (Vault) sont entièrement gérés par Docker, y compris leur configuration initiale.

## Architecture

Le projet est orchestré par `docker-compose.yml` et se compose de quatre services principaux :

1.  **`app`** : Le conteneur de l'application web, basée sur le micro-framework **Flask** en Python.
2.  **`db`** : Le conteneur de la base de données **MariaDB**, où sont stockés les utilisateurs et les données de l'application.
3.  **`vault`** : Le conteneur du coffre-fort **HashiCorp Vault**, qui contient les identifiants de la base de données.
4.  **`vault-setup`** : Un conteneur temporaire qui se lance une seule fois pour attendre que Vault soit prêt et y injecter automatiquement les secrets de la base de données.

Ce système est **100% automatisé** : une seule commande suffit pour lancer et configurer l'ensemble de l'environnement.

## Prérequis

*   [Docker](https://www.docker.com/products/docker-desktop/) doit être installé et en cours d'exécution sur votre machine.

## Installation et Lancement

L'ensemble du projet est conçu pour être lancé avec une seule commande.

1.  **Clonez le projet** (si ce n'est pas déjà fait) :
    ```bash
    git clone [URL_DU_PROJET]
    cd [NOM_DU_DOSSIER_PROJET]
    ```

2.  **Nettoyage initial (recommandé pour la première fois)** :
    Pour garantir qu'il n'y a pas d'anciens conteneurs, réseaux ou volumes en conflit, exécutez cette commande :
    ```bash
    docker-compose down -v
    ```

3.  **Lancez l'environnement complet** :
    Cette commande va construire l'image de l'application, télécharger les images nécessaires, créer les réseaux, et lancer tous les conteneurs dans le bon ordre.
    ```bash
    docker-compose up --build
    ```

    Le premier lancement peut prendre quelques minutes, le temps de télécharger les images.

    Vous pouvez suivre les logs des différents services dans le terminal. Attendez de voir le conteneur `vault-setup` se terminer avec un `exit code 0` et le conteneur `flask_app` afficher un message indiquant qu'il est en cours d'exécution sur le port 5000.

4.  **Accédez à l'application** :
    Une fois que tout est lancé, ouvrez votre navigateur et allez à l'adresse suivante :
    [http://localhost:5000](http://localhost:5000)

## Utilisation

1.  **Créer un compte** : Sur la page de connexion, cliquez sur "S'enregistrer" pour créer votre premier utilisateur.
2.  **Se connecter** : Utilisez les identifiants que vous venez de créer, et remplissez le captcha.
3.  **Configurer le 2FA** : Une fois connecté, un message vous invitera à activer la double authentification. Scannez le QR code avec votre application d'authentification.
4.  **Tester le 2FA** : Déconnectez-vous et reconnectez-vous. L'application vous demandera maintenant le code à 6 chiffres de votre application d'authentification après la saisie du mot de passe.
5.  **Tester l'anti-rejeu** : Essayez de soumettre un formulaire (ex: création de compte) puis de rafraîchir la page (ce qui renverrait les mêmes données POST). Vous devriez voir un message d'erreur indiquant que la requête est invalide ou a expiré.

## Stratégie de Détection des Comptes Obsolètes

La base de données contient une colonne `last_login_at` dans la table `users`, qui est mise à jour à chaque connexion réussie. Cela permet de mettre en place une stratégie de gouvernance :

*   **Définition** : Un compte est "inactif" après 90 jours sans connexion, et "obsolète" après 1 an.
*   **Phase 1 (Notification)** : Un script automatisé (tâche `cron`) pourrait envoyer un e-mail d'avertissement aux comptes inactifs.
*   **Phase 2 (Désactivation)** : Après 120 jours, les comptes pourraient être marqués comme inactifs dans la base de données (`is_active = FALSE`), empêchant la connexion.
*   **Phase 3 (Anonymisation/Suppression)** : Après 1 an, les données personnelles des comptes inactifs pourraient être anonymisées ou supprimées pour respecter les politiques de rétention des données (ex: RGPD).

Ce script de maintenance n'est pas inclus dans le projet de démonstration mais peut être facilement développé en se basant sur la colonne `last_login_at`.