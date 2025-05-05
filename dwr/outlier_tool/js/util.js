// Enable changing the class of an existing element (not natively supported in py shiny)
Shiny.addCustomMessageHandler('update_btn_class', function(data) {
    var btn = document.getElementById(data.id);
    if (btn) {
        btn.classList.remove(data.rm);
        btn.classList.add(data.add);
    }
});


// Set up keyboard shortcuts
document.addEventListener('keydown', function(event) {
    if (event.ctrlKey && event.key === 'z') {
        document.getElementById('btn_undo_flag').click();
    }
    if (event.ctrlKey && event.key === 'y') {
        document.getElementById('btn_redo_flag').click();
    }
});
