import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from numpy import array, linspace, pi, arange, sqrt
from utils.tutorial_utils import show_args
from qcodes.parameters import ManualParameter
from Modularize.support.UserFriend import *
from Modularize.support import QDmanager, Data_manager, cds, compose_para_for_multiplexing
from quantify_scheduler.gettables import ScheduleGettable
from quantify_core.measurement.control import MeasurementControl
from Modularize.support.Path_Book import find_latest_QD_pkl_for_dr, meas_raw_dir
from Modularize.support import init_meas, init_system_atte, shut_down, coupler_zctrl
from utils.tutorial_analysis_classes import ResonatorFluxSpectroscopyAnalysis
from Modularize.support.Pulse_schedule_library import One_tone_multi_sche, pulse_preview
from Modularize.support.QuFluxFit import plot_QbFlux_iq
from Modularize.analysis.raw_data_demolisher import fluxCav_dataReductor




def FluxCav_spec(QD_agent:QDmanager,meas_ctrl:MeasurementControl,flux_ctrl:dict,ro_elements:dict,flux_span:float=0.3,n_avg:int=300,flux_points:int=20,run:bool=True,Experi_info:dict={}):
    from numpy import NaN
    sche_func = One_tone_multi_sche
    freq_datapoint_idx = arange(0,len(list(list(ro_elements.values())[0])))
    original_rof = {}
    flux_dura = 0
    for q in ro_elements:
        qubit_info = QD_agent.quantum_device.get_element(q)
        qubit_info.measure.pulse_duration(100e-6)
        qubit_info.measure.integration_time(100e-6)
        qubit_info.reset.duration(250e-6)
        flux_dura = qubit_info.reset.duration()+qubit_info.measure.integration_time()
        original_rof[q] = qubit_info.clock_freqs.readout()
        qubit_info.clock_freqs.readout(NaN)

    flux_samples = sqrt(2)*linspace(-flux_span,flux_span,flux_points)/2.5
    freq = ManualParameter(name="freq", unit="Hz", label="Frequency")
    freq.batched = True
    bias = ManualParameter(name="bias", unit="V", label="Flux voltage")
    bias.batched = False
    
    spec_sched_kwargs = dict(   
        frequencies=ro_elements,
        R_amp=compose_para_for_multiplexing(QD_agent,ro_elements,1),
        R_duration=compose_para_for_multiplexing(QD_agent,ro_elements,3),
        R_integration=compose_para_for_multiplexing(QD_agent,ro_elements,4),
        R_inte_delay=compose_para_for_multiplexing(QD_agent,ro_elements,2),
        powerDep=False,
        bias = bias,
        bias_dura = flux_dura
    )

    

    
    if run:
        gettable = ScheduleGettable(
            QD_agent.quantum_device,
            schedule_function=sche_func, 
            schedule_kwargs=spec_sched_kwargs,
            real_imag=False,
            batched=True,
            num_channels=len(list(ro_elements.keys())),
        )
        QD_agent.quantum_device.cfg_sched_repetitions(n_avg)
        meas_ctrl.gettables(gettable)
        meas_ctrl.settables((freq,bias))
        meas_ctrl.setpoints_grid((freq_datapoint_idx,flux_samples)) # x0, x1
        
        rfs_ds = meas_ctrl.run("One-tone-Flux")
        for idx, q in enumerate(ro_elements):
            attr_0 = rfs_ds['x0'].attrs
            attr_1 = rfs_ds['x1'].attrs
            rfs_ds[f'x{2*idx}'] = array(list(ro_elements[q])*flux_samples.shape[0])
            rfs_ds[f'x{2*idx}'].attrs = attr_0
            
            rfs_ds[f'x{2*idx+1}'] = array([[i]*ro_elements[q].shape[0] for i in flux_samples]).reshape(-1)
            rfs_ds[f'x{2*idx+1}'].attrs = attr_1
            rfs_ds[f'x{2*idx+1}'].attrs['name'] = str(flux_ctrl[q])
            rfs_ds[f'x{2*idx+1}'].attrs['long_name'] = str(flux_ctrl[q])


        print(f"X : {array(rfs_ds.coords)}")
        print(f"Y : {array(rfs_ds.data_vars)}")

        # Save the raw data into netCDF
        nc_path = Data_manager().save_raw_data(QD_agent=QD_agent,ds=rfs_ds,qb=q,exp_type='FD',get_data_loc=True)
        
        if Experi_info != {}:
            show_args(Experi_info(q))
        
        # reset flux bias
        for q in ro_elements:
            flux_ctrl[q](0.0)
        
    else:
        n_s = 2
        preview_para = {}
        for q in ro_elements:
            preview_para[q] = ro_elements[q][:n_s]
        sweep_para2= array(flux_samples[:2])
        spec_sched_kwargs['frequencies']= preview_para
        spec_sched_kwargs['bias']= sweep_para2.reshape(sweep_para2.shape or (1,))[1]
        pulse_preview(QD_agent.quantum_device,sche_func,spec_sched_kwargs)

        if Experi_info != {}:
            show_args(Experi_info(q))
        nc_path = ''

    for q in ro_elements:
        QD_agent.quantum_device.get_element(q).clock_freqs.readout(original_rof[q])
    
    return nc_path

def update_flux_info_in_results_for(QD_agent:QDmanager,qb:str,FD_results:dict):
    qubit = QD_agent.quantum_device.get_element(qb)
    qubit.clock_freqs.readout(FD_results[qb].quantities_of_interest["freq_0"])
    QD_agent.Fluxmanager.save_sweetspotBias_for(target_q=qb,bias=FD_results[qb].quantities_of_interest["offset_0"].nominal_value)
    QD_agent.Fluxmanager.save_period_for(target_q=qb, period=2*pi/FD_results[qb].quantities_of_interest["frequency"].nominal_value)
    QD_agent.Fluxmanager.save_tuneawayBias_for(target_q=qb,mode='auto')
    QD_agent.Fluxmanager.save_cavFittingParas_for(target_q=qb,
        f=FD_results[qb].quantities_of_interest["frequency"].nominal_value,
        amp=FD_results[qb].quantities_of_interest["amplitude"].nominal_value,
        phi=FD_results[qb].quantities_of_interest["shift"].nominal_value,
        offset=FD_results[qb].quantities_of_interest["offset"].nominal_value
    )

def update_coupler_bias(QD_agent:QDmanager,cp_elements:dict):
    """
    Update the idle bias in Fluxmanager for couplers.\n
    --------------------------
    ### Args:\n
    cp_elements = {"c0":0.2}
    """
    for cp in cp_elements:
        QD_agent.Fluxmanager.save_idleBias_for(cp, cp_elements[cp])

def freq_arranger(QD_agent:QDmanager,freq_halfspan:dict,freq_shift:dict, fpts:int)->dict:
    """
    Generate the frequencies samples array with the rule: array = linspace(ROfreq+freq_shift-freq_halfspan, ROfreq+freq_shift+freq_halfspan, fpts)
    * frequency unit in Hz
    """
    ro_elements = {}
    for q in freq_halfspan:
        rof = QD_agent.quantum_device.get_element(q).clock_freqs.readout()
        ro_elements[q] = linspace(rof+freq_shift[q]-freq_halfspan[q], rof+freq_shift[q]+freq_halfspan[q], fpts)

    return ro_elements




def fluxCavity_executor(QD_agent:QDmanager,meas_ctrl:MeasurementControl,Fctrl:dict,ro_elements:dict,run:bool=True,flux_span:float=0.4,zpts=20,avg_n=20)->str:
    

    nc_path = FluxCav_spec(QD_agent,meas_ctrl,Fctrl,ro_elements,flux_span=flux_span,flux_points=zpts,run=run,n_avg=avg_n)


    return nc_path

# accident: q2, q3, q4

if __name__ == "__main__":
    
    """ Fill in """
    execution:bool = False
    chip_info_restore:bool = 0 # <- haven't been modified with the multiplexing version
    DRandIP = {"dr":"dr2","last_ip":"10"}
    cp_ctrl = {}
    freq_half_span = {
        "q0":5e6,
        "q1":5e6
    }
    freq_shift = {
        "q0":0e6,
        "q1":0e6
    }

    """ Optional paras """
    freq_data_points = 40
    flux_half_window_V  = 0.2
    flux_data_points = 40
    avg_n = 20
    

    
    """ Preparations """
    QD_path = find_latest_QD_pkl_for_dr(which_dr=DRandIP["dr"],ip_label=DRandIP["last_ip"])
    QD_agent, cluster, meas_ctrl, ic, Fctrl = init_meas(QuantumDevice_path=QD_path,mode='l',)
    chip_info = cds.Chip_file(QD_agent=QD_agent)
    ro_elements = freq_arranger(QD_agent, freq_half_span, freq_shift, freq_data_points)


    """ Running """
    update = False
    FD_results = {}

    Cctrl = coupler_zctrl(DRandIP["dr"],cluster,cp_ctrl)
    for qubit in ro_elements:
        init_system_atte(QD_agent.quantum_device,list([qubit]),ro_out_att=QD_agent.Notewriter.get_DigiAtteFor(qubit,'ro'))

    nc_path = fluxCavity_executor(QD_agent,meas_ctrl,Fctrl,ro_elements,run=execution,flux_span=flux_half_window_V, zpts=flux_data_points, avg_n=avg_n)
    cluster.reset()
    print(nc_path)
    if execution:
        import quantify_core.data.handling as dh
        dh.set_datadir(meas_raw_dir)
        dss = fluxCav_dataReductor(nc_path,list(ro_elements.keys()))
        ans = {}
        for q in dss:
            ans[q] = ResonatorFluxSpectroscopyAnalysis(tuid=dss[q].attrs["tuid"], dataset=dss[q]).run(sweetspot_index=0)

        permission = mark_input("Update the QD with this result ? [y/n]") 
        if permission.lower() in ['y','yes']:
            for qubit in ans:
                update_flux_info_in_results_for(QD_agent,qubit,ans[qubit])
            update_coupler_bias(QD_agent, cp_ctrl)
            update = True

    """ Storing """
    if update and execution:
        QD_agent.refresh_log("after FluxDep")
        QD_agent.QD_keeper()
        if chip_info_restore:
            pass
            # chip_info.update_FluxCavitySpec(qb=qubit, result=FD_results[qubit])
        update = False


    """ Close """
    print('Flux dependence done!')
    shut_down(cluster,Fctrl,Cctrl)