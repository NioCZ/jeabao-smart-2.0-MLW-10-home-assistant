# Jebao MLW Local pro Home Assistant

Custom integrace pro lokalni ovladani Jebao MLW wave pump pres Gizwits LAN protokol. Vychazi z overene komunikace v `jeabao-smart 2.0 MLW-10/test.py` a nepouziva cloud.

## Co integrace umi

- UDP discovery na portu `12414`
- TCP komunikace s pumpou na portu `12416`
- automaticke znovupripojeni po vypadku
- vice pump v jedne konfiguraci
- entity pro zapnuti/vypnuti, rezim, vykon, frekvenci, krmeni a diagnostiku
- oddelenou protokolovou vrstvu v `custom_components/jebao_mlw/api.py`, aby slo pozdeji doplnit dalsi Jebao profily

## Instalace pres HACS

1. Nahraj obsah tohoto adresare do GitHub repozitare.
2. V HACS otevri `Custom repositories`.
3. Pridej URL repozitare jako kategorii `Integration`.
4. Nainstaluj `Jebao MLW Local`.
5. Restartuj Home Assistant.
6. V `Settings > Devices & services` pridej integraci `Jebao MLW Local`.

Pokud nechas pole `Host` prazdne, integrace se pokusi najit vsechny pumpy na lokalni siti. Pro rucni konfiguraci zadej jednu nebo vice IP adres oddelenych carkou, napriklad:

```text
192.168.1.41, 192.168.1.42
```

## Rucni instalace

Zkopiruj slozku:

```text
custom_components/jebao_mlw
```

do Home Assistant konfigurace:

```text
/config/custom_components/jebao_mlw
```

Potom restartuj Home Assistant a pridej integraci z UI.

## Entity

Pro kazdou pumpu vznikne vlastni HA device a tyto entity:

- `switch` Pump
- `select` Mode
- `number` Flow
- `number` Frequency
- `number` Feed duration
- `button` Start feed mode
- `binary_sensor` Connected
- `sensor` Feed remaining
- `sensor` Last seen
- `sensor` Raw mode, ve vychozim stavu vypnuty v entity registry

## Podporovane rezimy

- Classic Pulse
- Classic Cross-flow
- Sine
- Random
- Constant
- Feed mode

## Poznamky k dalsim Jebao zarizenim

Zaklad discovery, TCP handshake a login jsou oddelene od MLW payloadu. Pro dalsi model se nejspis bude upravovat hlavne:

- `MODE_PROFILES`
- `MODE_FROM_RAW_BASE`
- `parse_mlw_state_from_frame`
- payloady v `MlwPumpClient.async_set_mode`, `async_set_power` a `async_start_feed`

Pokud dalsi Jebao zarizeni zustane na Gizwits LAN protokolu, melo by jit pridat jako dalsi profil bez prepisovani cele integrace.
