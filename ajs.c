/**
 * @file
 */
/******************************************************************************
 * Copyright (c) 2013, 2014, AllSeen Alliance. All rights reserved.
 *
 *    Permission to use, copy, modify, and/or distribute this software for any
 *    purpose with or without fee is hereby granted, provided that the above
 *    copyright notice and this permission notice appear in all copies.
 *
 *    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 *    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 *    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 *    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 *    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 *    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 *    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 ******************************************************************************/

#include "ajs.h"
#include "ajs_util.h"
#include "ajs_target.h"
#include "ajs_ctrlpanel.h"
#include "aj_util.h"

/**
 * Turn on per-module debug printing by setting this variable to non-zero value
 * (usually in debugger).
 */
#ifndef NDEBUG
uint8_t dbgAJS = 1;
#endif

static AJ_BusAttachment ajBus;

const char* AJS_AllJoynObject = "AJ";

/*
 * Initialization of the AllJoyn root object required for any application
 */
static const char aj_json[] =
    "{"
    "\"interfaceDefinition\":{},"
    "\"objectDefinition\":{},"
    "\"config\":{\"linkTimeout\":10000,\"callTimeout\":10000},"
    "\"METHOD\":0,"
    "\"SIGNAL\":1,"
    "\"PROPERTY\":2"
    "}";

static void ErrorHandler(duk_context* ctx, duk_errcode_t code, const char* msg)
{
    AJ_ErrPrintf(("ErrorHandler error code:%d %s\n", (int)code, msg));
#ifndef NDEBUG
    AJS_HeapDump();
#endif
    exit(0);
}

AJ_BusAttachment* AJS_GetBusAttachment()
{
    return &ajBus;
}

/*
 * Register builtin methods on the AJ object
 */
static void AJRegistrations(AJ_BusAttachment* aj, duk_context* ctx, duk_idx_t ajIdx)
{
    /*
     * Register message functions
     */
    AJS_RegisterMsgFunctions(aj, ctx, ajIdx);
    /*
     * Register native handler functions
     */
    AJS_RegisterHandlers(aj, ctx, ajIdx);
    /*
     * Register and initialize notification support
     */
    AJS_RegisterNotifHandlers(aj, ctx, ajIdx);
    /*
     * Register control panel support
     */
    AJS_RegisterControlPanelHandlers(aj, ctx, ajIdx);
}

static uint8_t ajRunning = FALSE;
static uint8_t busAttached = FALSE;

uint8_t AJS_IsRunning()
{
    return ajRunning;
}

static AJ_Status Run(AJ_BusAttachment* aj, duk_context* ctx)
{
    AJ_Status status = AJ_OK;
    duk_idx_t ajIdx = -1;

    if (duk_get_global_string(ctx, AJS_AllJoynObject)) {
        ajIdx = duk_get_top_index(ctx);
        /*
         * Add JavaScript objects and interfaces registered by the script
         */
        status = AJS_InitTables(ctx, ajIdx);
        /*
         * Register translations table
         */
        if (status == AJ_OK) {
            AJS_RegisterTranslations(ctx, ajIdx);
        }
    }
    while (status == AJ_OK) {
        /*
         * Attach our BusAttachment to an AllJoyn routing node
         */
        if (!busAttached) {
            AJS_HeapDump();
            status = AJS_AttachAllJoyn(aj);
            if (status == AJ_OK) {
                status = AJS_ConsoleInit(aj);
            }
            if (status == AJ_OK) {
                /*
                 * Bind the application session port
                 */
                status = AJ_BusBindSessionPort(aj, AJS_APP_PORT, NULL, AJ_FLAG_NO_REPLY_EXPECTED);
            }
            if (status != AJ_OK) {
                break;
            }
            busAttached = TRUE;
        }
        /*
         * Let JavaScript know we are attached to the bus
         */
        if (ajIdx >= 0) {
            ajRunning = TRUE;
            duk_get_prop_string(ctx, ajIdx, "onAttach");
            if (duk_is_callable(ctx, -1)) {
                duk_dup(ctx, ajIdx);
                if (duk_pcall_method(ctx, 0) != DUK_EXEC_SUCCESS) {
                    AJS_ConsoleSignalError(ctx);
                }
            }
            duk_pop(ctx);
        }
        /*
         * Start running
         */
        status = AJS_MessageLoop(ctx, aj, ajIdx);
    }
    AJ_WarnPrintf(("Exiting AJS main loop with status=%s\n", AJ_StatusText(status)));
    /*
     * JavaScript table entries are no longer valid
     */
    AJS_ResetTables(ctx);
    /*
     * Make sure the control panel service is terminated
     */
    AJS_CP_Terminate();
    /*
     * A RESTART_APP status indicates that the script engine must be restarted but we can keep our
     * existing BusAttachment.
     */
    if (status != AJ_ERR_RESTART_APP) {
        AJS_ConsoleTerminate();
        AJS_DetachAllJoyn(aj, status);
        busAttached = FALSE;
    }
    /*
     * If we told JavaScript we are attached now indicate we are detached
     */
    if (ajRunning) {
        duk_get_prop_string(ctx, ajIdx, "onDetach");
        if (duk_is_callable(ctx, -1)) {
            duk_dup(ctx, ajIdx);
            if (duk_pcall_method(ctx, 0) != DUK_EXEC_SUCCESS) {
                AJS_ConsoleSignalError(ctx);
            }
        }
        duk_pop(ctx);
        ajRunning = FALSE;
    }
    duk_pop_2(ctx);
    return status;
}

static const uint8_t icon[] = {
#include "icon.inc"
};

static duk_ret_t NativeOverrideAlert(duk_context* ctx)
{
    AJS_AlertHandler(ctx, 1 /* alert */);
    return 0;
}

static duk_ret_t NativeOverridePrint(duk_context* ctx)
{
    AJS_AlertHandler(ctx, 0 /* print */);
    return 0;
}

static void InitAllJoynObject(duk_context* ctx)
{
    duk_idx_t ajIdx;

    printf("InitAllJoynObject\n");
    duk_push_string(ctx, aj_json);
    duk_json_decode(ctx, -1);
    ajIdx = duk_get_top_index(ctx);
    /*
     * Register various functions and object on the AJ object
     */
    AJRegistrations(&ajBus, ctx, ajIdx);
    /*
     * Register AllJoyn with the global object
     */
    duk_put_global_string(ctx, AJS_AllJoynObject);
}

static duk_ret_t NativeModuleLoader(duk_context* ctx)
{
    const char* id = duk_require_string(ctx, 0);
    printf("Load module %s\n", id);

    if (strcmp(id, AJS_AllJoynObject) == 0) {
        InitAllJoynObject(ctx);
    } else if (strcmp(id, "IO") == 0) {
        /*
         * Register target-specific I/O functions
         */
        AJS_RegisterIO(ctx);
    } else {
        duk_push_sprintf(ctx, "Unknown module: \"%s\"\n", id);
        duk_throw(ctx);
    }
    return 0;
}

AJ_Status AJS_Main(const char* deviceName)
{
    AJ_Status status = AJ_OK;
    duk_context* ctx;
    duk_int_t ret;

    AJ_AboutSetIcon(icon, sizeof(icon), "image/jpeg", NULL);

    /*
     * Zero out the bus attachment
     */
    memset(&ajBus, 0, sizeof(ajBus));

    while (status == AJ_OK) {

        status = AJS_HeapCreate();
        if (status != AJ_OK) {
            break;
        }
        ctx = duk_create_heap(AJS_Alloc, AJS_Realloc, AJS_Free, &ctx, ErrorHandler);
        if (!ctx) {
            AJ_ErrPrintf(("Failed to create duktape heap\n"));
            status = AJ_ERR_RESOURCES;
            AJS_HeapDestroy();
            break;
        }
        AJS_HeapDump();
        /*
         * Register module loader (search) function with the Duktape object
         */
        duk_get_global_string(ctx, "Duktape");
        duk_push_c_function(ctx, NativeModuleLoader, 4);
        duk_put_prop_string(ctx, -2, "modSearch");
        duk_pop(ctx);
        /*
         * Override the builtin alert and print functions so we can redirect output to debug output
         * or the console if one is attached.
         */
        duk_push_c_function(ctx, NativeOverridePrint, DUK_VARARGS);
        duk_put_global_string(ctx, "print");
        duk_push_c_function(ctx, NativeOverrideAlert, DUK_VARARGS);
        duk_put_global_string(ctx, "alert");

        status = AJS_PropertyStoreInit(ctx, deviceName);
        if (status != AJ_OK) {
            AJ_ErrPrintf(("Failed to initialize property store\n"));
        }
        /*
         * Register setTimeout, setInterval timer functions.
         */
        AJS_RegisterTimerFuncs(ctx);
        /*
         * Evaluate the installed script
         */
        if (AJ_NVRAM_Exist(AJS_SCRIPT_NVRAM_ID)) {
            AJ_NV_DATASET* ds;
            /*
             * Read the script name if there is one
             */
            ds = AJ_NVRAM_Open(AJS_SCRIPT_NAME_NVRAM_ID, "r", 0);
            if (ds) {
                const char* scriptName = AJ_NVRAM_Peek(ds);
                if (scriptName) {
                    duk_push_string(ctx, scriptName);
                } else {
                    duk_push_string(ctx, "InstalledScript.js");
                }
                AJ_NVRAM_Close(ds);
            }
            /*
             * Now load the script
             */
            ds = AJ_NVRAM_Open(AJS_SCRIPT_NVRAM_ID, "r", 0);
            if (ds) {
                uint32_t len;
                const char* js;

                AJ_NVRAM_Read(&len, sizeof(len), ds);
                js = AJ_NVRAM_Peek(ds);
                ret = duk_pcompile_lstring_filename(ctx, 0, (const char*)js, len);
                AJ_NVRAM_Close(ds);
                if (ret == DUK_EXEC_SUCCESS) {
                    ret = duk_pcall(ctx, 0);
                }
                if (ret != DUK_EXEC_SUCCESS) {
                    AJS_ConsoleSignalError(ctx);
                    status = AJ_ERR_FAILURE;
                }
                duk_pop(ctx);
                if (status == AJ_OK) {
                    AJ_InfoPrintf(("Installed script from NVRAM\n"));
                } else {
                    AJ_ErrPrintf(("Deleting bad script from NVRAM\n"));
                    /*
                     * We don't want to repeatedly attempt to install a broken script
                     */
                    AJ_NVRAM_Delete(AJS_SCRIPT_NVRAM_ID);
                    status = AJ_ERR_RESTART_APP;
                }
                duk_gc(ctx, 0);
                AJS_HeapDump();
            } else {
                AJ_ErrPrintf(("Failed to read script from NVRAM\n"));
            }
        }
        if (status == AJ_OK) {
            status = Run(&ajBus, ctx);
        }
        if (status == AJ_ERR_RESTART_APP) {
            status = AJ_OK;
        }
        /*
         * The languages list was on the duktape heap so needs to be deregistered.
         */
        AJ_RegisterDescriptionLanguages(NULL);

        duk_destroy_heap(ctx);
        AJS_HeapDestroy();
    }
    return status;
}

