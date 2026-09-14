const stationBgClass = 'column-station';
const dateBgClass = 'column-datetime';
const analyteBgClass = 'column-analyte';
const analyteNameBgClass = 'column-analyte-name';
const analyteValueBgClass = 'column-analyte-value';
const outlierBgClass = 'column-outlier';

// Enable changing the class of an existing button (not natively supported in py shiny)
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

/**
 * There are a few instances where our app requires calling client-side code but
 * only after specific objects have finished rendering on the client. This object
 * is used to facilitate such interactions. It stores the object to wait for and
 * a callback function to execute when finished waiting.
 */
const shinyOutputUpdateManager = {
    expected: {}, // keys are id values we want to observe

    expectUpdate: function(outputId, functionToExecute) {
        this.expected[outputId] = {};
        this.expected[outputId].needs_update = true;
        this.expected[outputId].func = functionToExecute;
    },

    isExpecting: function(outputId) {
        return this.expected[outputId].needs_update === true;
    },

    clearExpectation: function(outputId) {
        this.expected[outputId].needs_update = false;
    },

    getCallback: function(outputId) {
        return this.expected[outputId].func;
    }
};

/**
 * Observes a DOM element for a period of inactivity after mutations, then executes a callback.
 * @param {string} elementSelector - CSS selector for the element to observe.
 * @param {function} onSettledCallback - Function to call when DOM changes have settled.
 * @param {number} debounceDelayMs - Milliseconds of inactivity to wait for.
 * @param {number} maxObservationTimeMs - Max time to observe before giving up.
 */
function observeUntilSettled(
    elementSelector,
    onSettledCallback,
    debounceDelayMs = 75,
    maxObservationTimeMs = 5000
) {
    const targetNode = document.querySelector(elementSelector);

    if (!targetNode) {
        console.warn(`Cannot observe: Element "${elementSelector}" not found.`);
        onSettledCallback(false);
        return;
    }

    let debounceTimer;
    let observer;

    const cleanup = (success) => {
        if (observer) {
            observer.disconnect();
            observer = null;
        }

        clearTimeout(debounceTimer);
        clearTimeout(overallTimeout);
        onSettledCallback(success);
    };

    const mutationObserverCallback = () => {
        clearTimeout(debounceTimer);

        debounceTimer = setTimeout(() => {
            cleanup(true);
        }, debounceDelayMs);
    };

    observer = new MutationObserver(mutationObserverCallback);

    const observerConfig = {
        childList: true,
        subtree: true
    };

    observer.observe(targetNode, observerConfig);

    const overallTimeout = setTimeout(() => {
        console.warn(`Max observation time reached for "${elementSelector}".`);
        cleanup(false);
    }, maxObservationTimeMs);
}

let columnTypes;

// Receive a message from the server telling us the check table will soon need to be updated.
Shiny.addCustomMessageHandler('update_column_label', function(data) {
    columnTypes = data.column_types;
    shinyOutputUpdateManager.expectUpdate('check_table', colorTableHeaders);
});

// Receive a message from the server telling us the export table will soon need
// outlier headers highlighted.
Shiny.addCustomMessageHandler('update_export_outlier_headers', function(data) {
    var outlierCols = data.outlier_cols;

    setTimeout(function() {
        colorExportOutlierHeaders('export_table', outlierCols);
    }, 100);
});

// Receive a message from the server telling us the export table header should be hidden.
Shiny.addCustomMessageHandler('remove_export_header', function(data) {
    shinyOutputUpdateManager.expectUpdate('export_table', hideTableHeaders);
});

/* Enable highlighting column headers in the check table */
function colorTableHeaders(tableId) {
    var tbl = document.getElementById(tableId);

    if (!tbl) {
        console.warn(`Table "${tableId}" not found.`);
        return;
    }

    var headerCells = tbl.getElementsByTagName('th');

    if (!headerCells) {
        console.warn('Table has no "th" elements.');
        return;
    }

    if (columnTypes.length != headerCells.length) {
        console.warn(
            `Could not color table headers due to length mismatch: ` +
            `${columnTypes.length} != ${headerCells.length}`
        );
        return;
    }

    for (var i = 0; i < headerCells.length; i++) {
        var cell = headerCells[i];
        var columnType = columnTypes[i];
        var bgClass = undefined;

        cell.classList.remove(
            stationBgClass,
            dateBgClass,
            analyteBgClass,
            analyteNameBgClass,
            analyteValueBgClass
        );

        if (columnType == 'station') {
            bgClass = stationBgClass;
        } else if (columnType == 'datetime') {
            bgClass = dateBgClass;
        } else if (columnType == 'analyte') {
            bgClass = analyteBgClass;
        } else if (columnType == 'analyte_name') {
            bgClass = analyteNameBgClass;
        } else if (columnType == 'analyte_value') {
            bgClass = analyteValueBgClass;
        }

        if (bgClass) {
            cell.classList.add(bgClass);
        }
    }
}

/* Highlight only generated outlier headers in the export table */
function colorExportOutlierHeaders(tableId, outlierCols) {
    var tbl = document.getElementById(tableId);

    if (!tbl) {
        console.warn(`Table "${tableId}" not found.`);
        return;
    }

    var headerCells = tbl.getElementsByTagName('th');

    if (!headerCells) {
        console.warn('Table has no "th" elements.');
        return;
    }

    for (var i = 0; i < headerCells.length; i++) {
        headerCells[i].classList.remove(outlierBgClass);

        if (outlierCols.includes(i)) {
            headerCells[i].classList.add(outlierBgClass);
        }
    }
}

function hideTableHeaders(tableId) {
    var tbl = document.getElementById(tableId);

    if (!tbl) {
        console.warn(`Table "${tableId}" not found.`);
        return;
    }

    var headerRows = tbl.getElementsByTagName('thead');

    if (!headerRows) {
        console.warn('Table has no "thead" elements.');
        return;
    }

    for (var i = 0; i < headerRows.length; i++) {
        var ele = headerRows[i];
        ele.style.visibility = 'collapse';
    }
}

/**
 * This function handles a signal from the server when server-side processing
 * is complete. We take this signal as a starting point to potentially wait for any
 * client-side processing to also complete before running custom functions.
 */
$(document).on('shiny:idle', function(event) {
    for (const outputId in shinyOutputUpdateManager.expected) {
        var userCallbackFunc =
            shinyOutputUpdateManager.getCallback(outputId);

        if (shinyOutputUpdateManager.isExpecting(outputId)) {
            shinyOutputUpdateManager.clearExpectation(outputId);

            observeUntilSettled(
                `#${outputId}`,
                (success) => {
                    if (success) {
                        userCallbackFunc(outputId);
                    } else {
                        console.warn(
                            `DOM observation for '${outputId}' concluded ` +
                            `without confirmed settlement or timed out.`
                        );
                    }
                }
            );
        }
    }
});

/**
 * Listen for clicks on trash icons, to allow the user to remove tests from the
 * test setup page.
 */
document.addEventListener('click', function(event) {
    const iconElement = event.target.closest(
        '.clickable-accordion-trash-icon'
    );

    if (iconElement) {
        event.stopPropagation();

        const panelValue = iconElement.getAttribute(
            'data-panel-value'
        );

        console.log(
            Shiny.setInputValue(
                'accordion_trash_icon_clicked',
                panelValue,
                {priority: 'event'}
            )
        );
    }
});

/**
 * TODO: finish this
 * Listen for clicks on accordions that define outlier tests - we want to record
 * whether they are open or not.
 */

/*
document.addEventListener('click', function(event) {
    const clicked = event.target.closest('.accordion-item');

    if (clicked) {
        const button_ele = clicked.querySelector('.accordion-button');
        console.log(button_ele);
    }
});
*/