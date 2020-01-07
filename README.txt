Tunnistuksen välityspalvelun esimerkki-integraatiosovellus palveluntarjoajalle

Tämä esimerkki tarjoaa helpon tavan testata OP:n tunnistuksen välityspalvelua hiekkalaatikko (sandbox) -ympäristössä.
Esimerkkiä voi ajaa Docker -ympäristössä tai ilman, jälkimmäisessä tapauksessa Python 3.7 ympäristö ja tarvittavat
kirjastot pitää olla asennettuna. 

Esimerkkitoteutuksen avulla tunnistuksen voi tehdä joko OP:n tunnistusseiän kautta tai valitsemalla pääsivulta suoraan
käytettävän tunnistusmenetelmän. Esimerkissä voidaan valita "consent" -parametri, joka tarkoittaa käytännössä sitä, että
ennen kuin tunnistuksessa välitettävät tiedot lähetetään palveluntarjoajalle, käyttäjä voi esikatsella ne ja hyväksyä
tai hylätä tietojen lähetyksen.

Tunnistuksen toteutuksesta

Hiekkalaatikko (sandbox) ympäristön endpointit

AUTHORIZE_ENDPOINT='https://isb-test.op.fi/oauth/authorize'
TOKEN_ENDPOINT='https://isb-test.op.fi/oauth/token'
ISBKEY_ENDPOINT='https://isb-test.op.fi/jwks/broker'
ISBEMBEDDED_ENDPOINT='https://isb-test.op.fi/api/embedded-ui/'

1) Hiekkalaatikko (sandbox) ympäristössä käytetään palveluntarjoajan puolella kiinteää avainparia. palveluntarjoaja 
   allekirjoittaa tunnistuspyynnön omalla salaisella avaimella ja lähettää sen tunnistuksen välityspalvelulle (http
   uudelleenohjaus)

   HUOM! Tuotannossa tunnistuksen välityspalvelu hakee palveluntarjoajan jwks end pointista palveluntarjoajan julkisen
   avaimen ja varmentaa allekirjoituksen ja käy katsomassa kumppanirekisteristä sopimustiedot, näitä tarkistuksia ei 
   tehdä hiekkalaatikossa (sandbox)  

   Tässä esimerkissä kohta @api.route("/authenticate")

2) Embedded toiminnossa lähetetään ylimääräinen attribuutti ftn_idp_id = <välineen nimi>, jonka perusteella tunnistuksen
   välityspalvelu osaa automaattisesti ohjata käyttäjän valitulle tunnistusvälineelle. Ylimääräisellä attribuutilla 
   prompt=consent kerrotaan tunnistuksen välityspalvelulle, että käyttäjä haluaa tarkistaa välitettävät tiedot

3) Tunnistuksen jälkeen tunnistuksen välityspalvelu tuottaa autentikaatiotokenin, allekirjoittaa sen omalla salaisella 
   avaimella ja salaa sen palveluntarjoajan julkisella avaimella (katso kohta HUOM! hiekkalaatikossa kiinteät avaimet) 
   ja lähettää tokenin palveluntarjoajalle (http uudelleenohjaus)

   Tässä esimerkissä kohta @api.route("/return")

4) Palveluntarjoaja hakee välityspalvelun jwsk -rajapinnasta välityspalvelun julkiset avaimet, katsoo tokenin 
   otsikkotiedoista (header) allekirjoitukseen käytetyn välityspalvelun avaimen, purkaa omalla salaisella avaimella 
   salauksen ja lopuksi tarkistaa allekirjoituksen välityspalvelun julkisella avaimella. Huom: käytetty allekirjoitus-
   avain on tarkistettava, koska avaimia voi olla avainrotaation takia useita. 

Tunnistuksen välityspalvelusta enemmän: https://github.com/op-developer/Identity-Service-Broker-API 
