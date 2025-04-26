# PORTAL Link™ Report Server

Tämä on PORTAL Link™ -järjestelmän Report Server, joka:

- Vastaanottaa agenttien skannaukset ja raportit
- Säilyttää ne hetkellisesti paikallisesti muistiin
- Siirtää ne edelleen GPT:n käyttöön Vercel Report API:in

## Käynnistys paikallisesti

```bash
uvicorn server:app --host 0.0.0.0 --port 8001