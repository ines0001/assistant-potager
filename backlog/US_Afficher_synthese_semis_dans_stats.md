# US — Afficher la synthèse des semis dans les statistiques

**Titre :** Afficher la synthèse des semis dans les statistiques potager

**Story :**
En tant que jardinier
Je veux voir dans la fenêtre des statistiques la liste de mes semis, classés par type de culture (végétatif ou reproducteur), avec les récoltes déjà réalisées sur ces cultures
Afin de suivre l'avancement de mes semis depuis la mise en terre jusqu'à la récolte

**Critères d'acceptance :**
- [ ] CA1 : La section "Semis" est affichée uniquement si au moins un semis est enregistré en base
- [ ] CA2 : Les semis sont séparés en deux sous-sections selon `culture_config` : "Récolte destructive (végétatif)" et "Récolte continue (reproducteur)"
- [ ] CA3 : Chaque ligne affiche la quantité semée, le nombre de semis, et si des récoltes existent, la quantité récoltée et le nombre de fois
- [ ] CA4 : Le compteur "Total : X événements" est supprimé de l'en-tête des statistiques
- [ ] CA5 : Les cultures sans entrée dans `culture_config` sont classées végétatif par défaut (comportement conservateur)

**Notes techniques :**
- Composants impactés : `bot/` (cmd_stats), `utils/stock.py` (nouvelle fonction `calcul_semis`)
- Migration BDD requise : non
- Dépendances : #US_Modéliser_type_organe_récolté, #US_Adapter_stock_selon_type_organe

**Estimation :** 2 points

**Scénario Gherkin :**
```gherkin
Given le jardinier a semé "radis" (50 graines) et "roquette" (20 graines)
And le jardinier a récolté 0.5 kg de roquette (2 fois)
When le jardinier appuie sur "Stats"
Then la section "Semis" apparaît dans les statistiques
And "radis" est en sous-section "Récolte destructive (végétatif)"
And "roquette" est en sous-section "Récolte continue (reproducteur)" avec "0.5 kg récoltés (2 fois)"
And le compteur "Total : X événements" n'est plus affiché