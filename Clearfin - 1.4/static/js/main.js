function abrirFormulario(tipo) {
    const formularios = document.querySelectorAll('.form-registro');
    formularios.forEach(form => form.style.display = 'none');
    
    const formTarget = document.getElementById('form-' + tipo);
    if (formTarget) {
        formTarget.style.display = 'block';
    }
}

function toggleRepeticao(checkbox) {
    const camposRepeticao = document.getElementById('campos-repeticao');
    if (camposRepeticao) {
        camposRepeticao.style.display = checkbox.checked ? 'block' : 'none';
    }
}

