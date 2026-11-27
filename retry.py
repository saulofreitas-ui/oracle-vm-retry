#!/usr/bin/env python3
"""
Tenta criar uma VM Ampere A1 (Always Free) na Oracle Cloud até conseguir.
Alterna entre 1 OCPU/6 GB, 2 OCPU/12 GB e 4 OCPU/24 GB.

Todos os dados da conta vêm de GitHub Secrets:
  OCI_SETTINGS (JSON) -> user, fingerprint, tenancy, region, compartment_id,
                         availability_domain, subnet_id, image_id, ssh_public_key
  OCI_KEY             -> conteúdo do arquivo .pem da chave de API
Opcionais:
  NTFY_TOPIC   -> aviso no celular pelo app ntfy
  MAX_MINUTES  -> quanto tempo esta execução fica tentando (padrão 25)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

import oci

SHAPE = "VM.Standard.A1.Flex"
SHAPES = [(1, 6), (2, 12), (4, 24)]
INTERVALO = 60
INTERVALO_429 = 180
DISPLAY_NAME = "vm-ampere-free"
BRT = timezone(timedelta(hours=-3))


def log(msg):
    print(f"[{datetime.now(BRT):%d/%m %H:%M:%S}] {msg}", flush=True)


def gh_output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}<<EOF\n{value}\nEOF\n")


def gh_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(text + "\n")


def notificar(titulo, texto):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=texto.encode(), headers={"Title": titulo})
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        log(f"(falha ao notificar: {e})")


def a1_existente(compute, comp):
    insts = oci.pagination.list_call_get_all_results(compute.list_instances, compartment_id=comp).data
    for i in insts:
        if i.shape == SHAPE and i.lifecycle_state not in ("TERMINATED", "TERMINATING"):
            return i
    return None


def ip_publico(compute, network, comp, inst_id):
    for _ in range(60):
        inst = compute.get_instance(inst_id).data
        if inst.lifecycle_state == "RUNNING":
            for va in compute.list_vnic_attachments(comp, instance_id=inst_id).data:
                if va.lifecycle_state == "ATTACHED":
                    ip = network.get_vnic(va.vnic_id).data.public_ip
                    if ip:
                        return ip
        time.sleep(10)
    return None


def finalizar(compute, network, comp, inst, cfg_txt):
    # O repositório é público: o IP NÃO vai para log/issue, só para o aviso privado (ntfy).
    log(f"VM encontrada/criada ({cfg_txt}) – aguardando ficar RUNNING...")
    ip = ip_publico(compute, network, comp, inst.id) or "(sem IP ainda – veja no console)"
    publico = (
        f"VM criada! {cfg_txt}\n"
        f"Nome: {inst.display_name}\n"
        f"IP: veja no console da Oracle (Compute > Instances)\n"
        f"Acesso: ssh -i oracle_vm_key ubuntu@IP_DA_VM"
    )
    log(publico)
    gh_output("created", "true")
    gh_output("message", publico)
    gh_summary("## ✅ " + publico.replace("\n", "  \n"))
    notificar("VM Oracle criada!", publico.replace("IP: veja no console da Oracle (Compute > Instances)", f"IP: {ip}")
              .replace("IP_DA_VM", ip))


def main():
    s = json.loads(os.environ["OCI_SETTINGS"])
    comp = s["compartment_id"]
    config = {
        "user": s["user"],
        "fingerprint": s["fingerprint"],
        "tenancy": s["tenancy"],
        "region": s["region"],
        "key_content": os.environ["OCI_KEY"],
    }
    oci.config.validate_config(config)
    compute = oci.core.ComputeClient(config)
    network = oci.core.VirtualNetworkClient(config)

    existente = a1_existente(compute, comp)
    if existente:
        finalizar(compute, network, comp, existente, "já existia na conta")
        return

    limite = time.time() + float(os.environ.get("MAX_MINUTES", "25")) * 60
    n = int(time.time() // 60)  # varia a forma inicial entre execuções
    tentativas = 0
    while time.time() < limite:
        ocpus, mem = SHAPES[n % len(SHAPES)]
        n += 1
        tentativas += 1
        cfg_txt = f"{ocpus} OCPU / {mem} GB"
        details = oci.core.models.LaunchInstanceDetails(
            availability_domain=s["availability_domain"],
            compartment_id=comp,
            display_name=DISPLAY_NAME,
            shape=SHAPE,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=ocpus, memory_in_gbs=mem),
            source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=s["image_id"]),
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=s["subnet_id"], assign_public_ip=True),
            metadata={"ssh_authorized_keys": s["ssh_public_key"]},
        )
        espera = INTERVALO
        try:
            inst = compute.launch_instance(details).data
            finalizar(compute, network, comp, inst, cfg_txt)
            return
        except oci.exceptions.ServiceError as e:
            msg = (e.message or "").lower()
            if e.status == 429:
                log(f"#{tentativas} {cfg_txt}: muitas requisições (429)")
                espera = INTERVALO_429
            elif e.status == 500 and "capacity" in msg:
                log(f"#{tentativas} {cfg_txt}: sem capacidade")
            elif e.status in (401, 404) and "notauthenticated" in (e.code or "").lower():
                log(f"ERRO de autenticação ({e.code}): confira os secrets OCI_*. {e.message}")
                sys.exit(1)
            else:
                existente = a1_existente(compute, comp)
                if existente:
                    finalizar(compute, network, comp, existente, "criada por outro caminho")
                    return
                log(f"#{tentativas} {cfg_txt}: erro {e.status} {e.code} – {e.message}")
        except Exception as e:
            log(f"#{tentativas} {cfg_txt}: erro inesperado – {e}")
        time.sleep(espera)

    log(f"Fim desta execução: {tentativas} tentativas sem vaga. A próxima execução continua.")
    gh_summary(f"Sem vaga nesta execução ({tentativas} tentativas).")


if __name__ == "__main__":
    main()
