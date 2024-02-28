import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from numpy import array, linspace
from Modularize.support import build_folder_today
from Modularize.path_book import meas_raw_dir
from Modularize.Pulse_schedule_library import One_tone_sche, pulse_preview
from quantify_core.analysis.spectroscopy_analysis import ResonatorSpectroscopyAnalysis
from utils.tutorial_utils import show_args
from qcodes.parameters import ManualParameter
from quantify_scheduler.gettables import ScheduleGettable
from Modularize.support import QuantumDevice, get_time_now
from quantify_core.measurement.control import MeasurementControl
import os

def Cavity_spec(quantum_device:QuantumDevice,meas_ctrl:MeasurementControl,ro_bare_guess:dict,ro_span_Hz:int=15e6,n_avg:int=300,points:int=200,run:bool=True,q:str='q1',Experi_info:dict={})->dict:
    """
        Do the cavity search by the given QuantumDevice with a given target qubit q. \n
        Please fill up the initial value about measure for qubit in QuantumDevice first, like: amp, duration, integration_time and acqusition_delay! 
    """
    sche_func = One_tone_sche
    qubit_info = quantum_device.get_element(q)
    analysis_result = {}
    ro_f_center = ro_bare_guess[q]
    ro_f_samples = linspace(ro_f_center-ro_span_Hz,ro_f_center+ro_span_Hz,points)
    freq = ManualParameter(name="freq", unit="Hz", label="Frequency")
    freq.batched = True
    
    spec_sched_kwargs = dict(   
        frequencies=freq,
        q=q,
        R_amp={str(q):qubit_info.measure.pulse_amp()},
        R_duration={str(q):qubit_info.measure.pulse_duration()},
        R_integration={str(q):qubit_info.measure.integration_time()},
        R_inte_delay=qubit_info.measure.acq_delay(),
        powerDep=False,
    )
    exp_kwargs= dict(sweep_F=['start '+'%E' %ro_f_samples[0],'end '+'%E' %ro_f_samples[-1]],
                     )
    
    if run:
        gettable = ScheduleGettable(
            quantum_device,
            schedule_function=sche_func, 
            schedule_kwargs=spec_sched_kwargs,
            real_imag=False,
            batched=True,
        )
        quantum_device.cfg_sched_repetitions(n_avg)
        meas_ctrl.gettables(gettable)
        meas_ctrl.settables(freq)
        meas_ctrl.setpoints(ro_f_samples)
        
        rs_ds = meas_ctrl.run("One-tone")
        analysis_result[q] = ResonatorSpectroscopyAnalysis(tuid=rs_ds.attrs["tuid"], dataset=rs_ds).run()
        # save the xarrry into netCDF
        exp_timeLabel = get_time_now()
        raw_folder = build_folder_today(meas_raw_dir)
        rs_ds.to_netcdf(os.path.join(raw_folder,f"{q}_CavitySpectro_{exp_timeLabel}.nc"))
        print(f"Raw exp data had been saved into netCDF with the time label '{exp_timeLabel}'")

        print(f"{q} Cavity:")
        show_args(exp_kwargs, title="One_tone_kwargs: Meas.qubit="+q)
        if Experi_info != {}:
            show_args(Experi_info(q))
        
    else:
        n_s=2 
        sweep_para= array(ro_f_samples[:n_s])
        spec_sched_kwargs['frequencies']= sweep_para.reshape(sweep_para.shape or (1,))
        pulse_preview(quantum_device,sche_func,spec_sched_kwargs)
        

        show_args(exp_kwargs, title="One_tone_kwargs: Meas.qubit="+q)
        if Experi_info != {}:
            show_args(Experi_info(q))
    return analysis_result

if __name__ == "__main__":
    from Modularize.support import init_meas, init_system_atte, shut_down
    from Modularize.path_book import qdevice_backup_dir
    from numpy import NaN
    

    # Reload the QuantumDevice or build up a new one
    QD_path = ''
    QDmanager, cluster, meas_ctrl, ic = init_meas(QuantumDevice_path=QD_path,mode='n')
    
    # TODO: keep the particular bias into chip spec, and it should be fast loaded
    Fctrl: callable = {
        "q0":cluster.module2.out0_offset,
        "q1":cluster.module2.out1_offset,
        "q2":cluster.module2.out2_offset,
        "q3":cluster.module2.out3_offset,
        # "q4":cluster.module10.out0_offset
    }
    # default the offset in circuit
    for i in Fctrl:
        Fctrl[i](0.0)
    # Set the system attenuations
    ro_out_att = 20
    xy_out_att = 10
    init_system_atte(QDmanager.quantum_device,list(Fctrl.keys()), ro_out_att, xy_out_att)
    for i in range(6):
        getattr(cluster.module8, f"sequencer{i}").nco_prop_delay_comp_en(True)
        getattr(cluster.module8, f"sequencer{i}").nco_prop_delay_comp(50)
    # guess
    ro_bare=dict(
        q0 = 5.72e9,
        q1 = 6e9,
        q2 = 5.81e9,
        q3 = 6.1e9,
    )
    # q4 = 5.9e9,
    error_log = []
    for qb in ro_bare:
        print(qb)
        qubit = QDmanager.quantum_device.get_element(qb)
        if QD_path == '':
            qubit.reset.duration(150e-6)
            qubit.measure.acq_delay(0)
            qubit.measure.pulse_amp(0.1)
            qubit.measure.pulse_duration(2e-6)
            qubit.measure.integration_time(2e-6)
        else:
            # avoid freq conflicts
            qubit.clock_freqs.readout(NaN)
        CS_results = Cavity_spec(QDmanager.quantum_device,meas_ctrl,ro_bare,q=qb)
        if CS_results != {}:
            print(f'Cavity {qb} @ {CS_results[qb].quantities_of_interest["fr"].nominal_value} Hz')
            QDmanager.quantum_device.get_element(qb).clock_freqs.readout(CS_results[qb].quantities_of_interest["fr"].nominal_value)
        else:
            error_log.append(qb)
    print(f"Cavity Spectroscopy error qubit: {error_log}")

    QDmanager.refresh_log("q2 absent!")
    QDmanager.QD_keeper()
    print('CavitySpectro done!')
    
    restore = False
    chip_name = '5Qtest7'
    chip_type = "5Q"
    if restore == True:
        import chip_data_store as cds
        chip_info = cds.Chip_file(chip_name, chip_type, QD_path, ro_out_att, xy_out_att)
        
    
    shut_down(cluster,Fctrl)
    
