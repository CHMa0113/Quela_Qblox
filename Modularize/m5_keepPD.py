import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from Modularize.support import QDmanager
from Modularize.support.Path_Book import find_latest_QD_pkl_for_dr

def fillin_PDans(QD_path:str,ans:dict):
    """
    Fill in the power dep answer to the quantum_device.\n
    format:\n
    `ans = {"q0":{"dressF_Hz":,"dressP":,"bareF_Hz":},...}`
    """
    QDagent = QDmanager(QD_path)
    QDagent.QD_loader()
    for q in ans:
        qubit = QDagent.quantum_device.get_element(q)
        if ans[q]["dressP"] != "": qubit.measure.pulse_amp(ans[q]["dressP"]) 
        if ans[q]["dressF_Hz"] != "": qubit.clock_freqs.readout(ans[q]["dressF_Hz"])
        if ans[q]["bareF_Hz"] != "": QDagent.Notewriter.save_bareFreq_for(target_q=q,bare_freq=ans[q]["bareF_Hz"])
        if ans[q]["ro_atte"] != "": QDagent.Notewriter.save_DigiAtte_For(atte_dB=ans[q]["ro_atte"],target_q=q,mode='ro')

    QDagent.refresh_log("PD answer stored!")
    QDagent.QD_keeper()


if __name__ == "__main__":
    """ Fill in """
    DRandIP = {"dr":"dr3","last_ip":"13"}
    PDans = {
    #   "q0":{"dressF_Hz":5.90987e9,"dressP":0.3,"bareF_Hz":5.90593e9,"ro_atte":40},
    #   "q1":{"dressF_Hz":6.01316e9,"dressP":0.6,"bareF_Hz":6.00985e9,"ro_atte":44},
    #   "q2":{"dressF_Hz":5.86154e9,"dressP":0.3,"bareF_Hz":5.85791e9,"ro_atte":40},
        "q3":{"dressF_Hz":6.03994e9,"dressP":0.6,"bareF_Hz":6.03622e9,"ro_atte":50},
    }
    
    
    """ Storing """
    QD_path = find_latest_QD_pkl_for_dr(which_dr=DRandIP["dr"],ip_label=DRandIP["last_ip"])
    fillin_PDans(QD_path, PDans)
    
    
