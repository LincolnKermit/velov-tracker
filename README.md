# README

<!-- LATEST:START -->
<!-- This section is updated automatically every 15 minutes by the collect workflow. -->
### 🚲 Latest update

**Latest update:** 00:42 on 19/07/2026 (Local timezone)

- Electrical bikes available: **1769**
- Mechanical bikes available: **2011**
- Total bikes available: **3782**
- Free parking stands: **5390**
- Stations open: **453/455**

**Dynamic data powered by Github Actions 🤖**
<!-- LATEST:END -->

### 📈 Availability over the last 24 hours

Total, electrical and mechanical bikes available across Lyon — the lowest point is marked in red.

![Bikes available across Lyon over the last 24 hours](assets/availability.svg)

### 🗺️ Electrical bikes by arrondissement over the last 24 hours

Electrical Vélo'v bikes available in each of Lyon's nine arrondissements — one line per arrondissement.

![Electrical bikes available by arrondissement over the last 24 hours](assets/availability_by_arrondissement.svg)

## French version

Ce projet a été réalisé afin de traquer la tendance de la disponibilité des stations Velo'v à Lyon au cours de la journée.


### Fonctionnalités actuelles:

- Avoir une carte avec l'ensemble des informations suivantes:
    - Nombre de velo'v mécaniques disponibles
    - Nombre de velo'v éléctriques disponibles
    - Nombre de places disponible
    - Ajouter un système de filtre/tri sur la page afin de trier les résultats.
    - API disponible - 24h d'historique d'une station ( localhost:5000/history/<station_id> )
    - GitHub Actions pour recueillir automatiquement des données.

### Roadmap:

- [ ] Ajouter un système de filtre/tri sur la page afin de trier les résultats.
- [ ] Ajouter une solution de stockage afin d'enregistrer les données et de les ré-utiliser par la suite.


### Capture d'écran

<img width="1124" height="725" alt="image" src="https://github.com/user-attachments/assets/9dcad849-dd21-4e69-86a0-3b31a3c9968a" />
