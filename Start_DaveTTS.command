#!/bin/bash

# Spostati nella cartella in cui si trova questo script
cd "$(dirname "$0")"

echo "======================================"
# Avviso di avvio DaveTTS
echo "    Avvio di DaveTTS (Docker)         "
# ======================================
echo "======================================"
echo ""

# Avvia docker compose usando il file specifico per il Mac (che espone le porte ed ha percorsi relativi)
docker-compose -f docker-compose.mac.yml up -d --build

echo ""
echo "Applicazione avviata con successo!"
echo "Puoi accedere dal tuo browser alla porta configurata."
echo ""
echo "Questa finestra si chiuderà automaticamente tra 5 secondi..."
sleep 5
