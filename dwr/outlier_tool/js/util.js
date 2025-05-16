const dateBgClass = 'bg-success';
const numBgClass = 'bg-primary';

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


/*
 * There are a few instances where our app requires calling client-side code but
 * only after specific objects have finished rendering on the client. This object
 * is used to facilitate such interactions. It stores the object to wait for and
 * a callback function to execute when finished waiting.
 */
const shinyOutputUpdateManager = {
    expected: {}, // keys are id values we want to observe

    // This function enables client-side output checking
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

/*
 * Observes a DOM element for a period of inactivity after mutations, then executes a callback.
 * @param {string} elementSelector - CSS selector for the element to observe.
 * @param {function} onSettledCallback - Function to call when DOM changes have settled.
 * @param {number} debounceDelayMs - Milliseconds of inactivity to wait for.
 * @param {number} maxObservationTimeMs - Max time to observe before giving up.
 */
function observeUntilSettled(elementSelector,
                             onSettledCallback,
                             debounceDelayMs = 75,
                             maxObservationTimeMs = 5000
) {
    const targetNode = document.querySelector(elementSelector);

    if (!targetNode) {
        console.warn(`Cannot observe: Element "${elementSelector}" not found.`);
        onSettledCallback(false); // Indicate failure
        return;
    }

    let debounceTimer;
    let observer;

    // Create a cleanup function to handle timer functions (which are internal
    // to this observeUntilSettled function) and also pass along the "success"
    // status to the onSettledCallback.
    const cleanup = (success) => {
        if (observer) {
            observer.disconnect();
            observer = null; // Help garbage collection
        }
        clearTimeout(debounceTimer);
        clearTimeout(overallTimeout); // Clear the safety timeout
        onSettledCallback(success);
    };

    const mutationObserverCallback = (mutationsList, obs) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            cleanup(true); // Success
        }, debounceDelayMs);
    };

    observer = new MutationObserver(mutationObserverCallback);

    const observerConfig = {
        childList: true, // For when Shiny replaces/updates children
        subtree: true    // Good to have if object rendering involves multiple nested changes
    };

    observer.observe(targetNode, observerConfig);

    // Safety net: stop observing after a max time to prevent lingering observers
    const overallTimeout = setTimeout(() => {
        console.warn(`Max observation time reached for "${elementSelector}".`);
        cleanup(false); // Indicate potential failure or timeout
    }, maxObservationTimeMs);
}


let columnTypes;

// Receive a message from the server telling us the table will soon need to be updated.
Shiny.addCustomMessageHandler('update_column_label', function(data) {
    columnTypes = data.column_types; // TODO: refactor to not use global
    shinyOutputUpdateManager.expectUpdate('check_table', colorTableHeaders);
});

// Receive a message from the server telling us the table will soon need to be updated.
Shiny.addCustomMessageHandler('remove_export_header', function(data) {
    shinyOutputUpdateManager.expectUpdate('export_table', hideTableHeaders);
});


/* Enable highlighting columns headers in the 'check' table */
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
        console.warn(`Could not color table headers due to length mismatch: ${columnTypes.length} != ${headerCells.length}`);
        return;
    }

    for (var i = 0; i < headerCells.length; i++) {
        var cell = headerCells[i];
        var columnType = columnTypes[i];

        var bgClass = undefined;

        if (columnType == 'numeric') {
            bgClass = numBgClass;
        } else if (columnType == 'datetime') {
            bgClass = dateBgClass;
        }

        if (bgClass) {
            cell.classList.add(bgClass)
        }
    }
}

function hideTableHeaders(tableId) {
    var tbl = document.getElementById(tableId);
    if (!tbl) {
        console.warn(`Table "${tableId}" not found.`);
        return;
    }

    var headerRows = tbl.getElementsByTagName('thead'); // should only return 1 element...
    if (!headerRows) {
        console.warn('Table has no "thead" elements.');
        return;
    }

    for (var i = 0; i < headerRows.length; i++) {
        var ele = headerRows[i];
        ele.style.visibility = 'collapse';
    }
}


/*
 * This function handles a signal from the server when server-side processing
 * is complete. We take this signal as a starting point to (potentially) wait for any
 * client-side processing to also complete before running custom functions.
 */
$(document).on('shiny:idle', function(event) {
    for (const outputId in shinyOutputUpdateManager.expected) {
        userCallbackFunc = shinyOutputUpdateManager.getCallback(outputId);

        // Most often, no items will be expecting to be updated, so we check for it.
        if (shinyOutputUpdateManager.isExpecting(outputId)) {

            // Clear the expectation *before* starting observation to prevent
            // re-triggering if shiny:idle fires multiple times quickly or if
            // observation is very short.
            shinyOutputUpdateManager.clearExpectation(outputId);

            observeUntilSettled(
                `#${outputId}`, // css selector
                (success) => {
                    if (success) {
                        userCallbackFunc(outputId);
                    } else {
                        console.warn(`DOM observation for '${outputId}' concluded without confirmed settlement or timed out.`);
                    }
                }
            );
        }
    }
});

/*
 * Listen for clicks on trash icons, to allow the user to remove tests from the
 * test setup page.
 */
document.addEventListener('click', function(event) {
    const iconElement = event.target.closest('.clickable-accordion-trash-icon');

    if (iconElement) {
        // Prevent the event from bubbling up to other elements
        event.stopPropagation();

        const panelValue = iconElement.getAttribute('data-panel-value');
        console.log(Shiny.setInputValue(
            "accordion_trash_icon_clicked",
            panelValue,
            { priority: "event" }
        ));
    }
});

/*
 * Enable "help" tab to glow when it's mentioned in a tooltip. The tooltip is
 * created dynamically, so we have to observe for it.
 */
const tooltip_observer = new MutationObserver((mutations, obs) => {
    const tooltip = document.getElementById('test_tooltip');
    if (tooltip) {
        // Attach hover listeners
        const targetLink = document.querySelector('a[data-value="help_tab"]');
        if (targetLink) {
            tooltip.addEventListener('mouseenter', () => {
                targetLink.classList.add('glow');
            });
            tooltip.addEventListener('mouseleave', () => {
                targetLink.classList.remove('glow');
            });
        }
        // Note: we don't want to disconnect the observer since the tooltip
        // is recreated each time the file changes on the test page, so we
        // need to re-add the listeners.
    }
});

tooltip_observer.observe(document.body, { childList: true, subtree: true });


/*
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
